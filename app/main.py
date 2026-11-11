import json
import logging
import secrets
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from aiogram import Bot
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from app.config import settings
from app import database
from app.menus import send_home_widget
from app.telegram_api import call
from app.ludo_engine import GameState, PlayerState, legal_moves, move_token, next_turn, choose_ai_move

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("ludo_arena")
bot = Bot(token=settings.bot_token)

COLORS = ("red", "green")
COLOR_LABELS = {"red": "You", "green": "Arena AI"}
MAX_GAME_AGE_SECONDS = 60 * 60 * 4


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect_db()
    me = await bot.get_me()
    log.info("Connected as @%s", me.username)
    if settings.webhook_base_url:
        if not settings.webhook_secret:
            raise RuntimeError("WEBHOOK_SECRET is required when WEBHOOK_BASE_URL is set")
        url = settings.webhook_base_url.rstrip("/") + "/telegram/webhook"
        await bot.set_webhook(url=url, secret_token=settings.webhook_secret,
                              allowed_updates=["message", "widget_query"])
        log.info("Webhook configured: %s", url)
    yield
    if settings.webhook_base_url:
        await bot.delete_webhook(drop_pending_updates=False)
    await bot.session.close()
    await database.close_db()


app = FastAPI(title="Ludo Arena API", version="2.0.0", lifespan=lifespan)


@app.get("/")
async def home():
    return {"status": "ok", "service": "ludo-arena", "phase": 2}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ludo-arena", "phase": 2}


async def register_user(tg_user: dict):
    now = datetime.now(timezone.utc)
    user = await database.db.users.find_one_and_update(
        {"telegram_id": tg_user["id"]},
        {"$set": {
            "first_name": tg_user.get("first_name", "Player"),
            "last_name": tg_user.get("last_name"),
            "username": tg_user.get("username"),
            "language_code": tg_user.get("language_code"),
            "last_seen": now,
        }, "$setOnInsert": {
            "telegram_id": tg_user["id"], "coins": 0, "wins": 0, "losses": 0,
            "level": 1, "xp": 0, "created_at": now,
        }}, upsert=True, return_document=True)
    return user


def state_from_doc(doc: dict) -> GameState:
    return GameState(
        players=[PlayerState(p["color"], list(p["tokens"])) for p in doc["players"]],
        current_player=int(doc.get("current_player", 0)),
        last_roll=doc.get("last_roll"),
        status=doc.get("status", "active"),
    )


def game_payload(doc: dict, message: str = "") -> dict:
    state = state_from_doc(doc)
    player = state.players[state.current_player]
    dice = state.last_roll
    return {
        "screen": "game",
        "game_id": str(doc["_id"]),
        "message": message or ("Your turn — roll the dice" if state.current_player == 0 else "Arena AI is thinking…"),
        "current_player": state.current_player,
        "current_color": player.color,
        "dice": dice,
        "legal_moves": legal_moves(player, dice) if dice else [],
        "players": [{"color": p.color, "tokens": p.tokens} for p in state.players],
        "status": state.status,
    }


async def save_game(user_id: int, state: GameState, message: str = "") -> dict:
    now = datetime.now(timezone.utc)
    doc = {
        "telegram_id": user_id,
        "players": [{"color": p.color, "tokens": p.tokens} for p in state.players],
        "current_player": state.current_player,
        "last_roll": state.last_roll,
        "status": state.status,
        "updated_at": now,
        "created_at": now,
    }
    result = await database.db.games.insert_one(doc)
    doc["_id"] = result.inserted_id
    doc["_message"] = message
    return doc


async def start_solo_game(user_id: int) -> dict:
    await database.db.games.update_many(
        {"telegram_id": user_id, "status": "active"},
        {"$set": {"status": "abandoned", "updated_at": datetime.now(timezone.utc)}},
    )
    state = GameState(players=[PlayerState("red"), PlayerState("green")])
    doc = await save_game(user_id, state, "Match started! You are Red. Roll a six to bring a token out.")
    return game_payload(doc, doc["_message"])


async def get_active_game(user_id: int):
    return await database.db.games.find_one(
        {"telegram_id": user_id, "status": "active"},
        sort=[("updated_at", -1)],
    )


async def play_ai_turn(state: GameState, dice: int) -> str:
    notes = []
    roll = dice
    consecutive_sixes = 0
    while state.status == "active" and state.current_player == 1:
        moves = legal_moves(state.players[1], roll)
        if moves:
            token = choose_ai_move(state.players[1], roll)
            captured = move_token(state, 1, token, roll)
            if state.status == "finished":
                return "Arena AI won this match."
            notes.append(f"AI moved token {token + 1} by {roll}")
            if captured:
                notes.append("AI captured one of your tokens")
        else:
            notes.append(f"AI rolled {roll}; no valid move")
        if roll == 6 and moves and consecutive_sixes < 2:
            consecutive_sixes += 1
            roll = secrets.randbelow(6) + 1
            continue
        state.current_player = 0
        state.last_roll = None
        break
    return ". ".join(notes) or "Your turn."


async def widget_game_action(user_id: int, action: dict) -> dict:
    kind = action.get("action")
    if kind == "solo":
        return await start_solo_game(user_id)
    doc = await get_active_game(user_id)
    if not doc:
        return {"screen": "home", "message": "No active match. Start Solo Challenge first."}
    state = state_from_doc(doc)
    if kind == "roll":
        if state.status != "active" or state.current_player != 0 or state.last_roll is not None:
            return game_payload(doc, "Wait for your turn or choose a token for the current roll.")
        dice = secrets.randbelow(6) + 1
        state.last_roll = dice
        moves = legal_moves(state.players[0], dice)
        if not moves:
            state.current_player = 1
            state.last_roll = None
            message = f"You rolled {dice}; no valid move."
            ai_dice = secrets.randbelow(6) + 1
            message += " " + await play_ai_turn(state, ai_dice)
        else:
            message = f"You rolled {dice}. Choose a highlighted token."
        await database.db.games.update_one({"_id": doc["_id"]}, {"$set": {
            "players": [{"color": p.color, "tokens": p.tokens} for p in state.players],
            "current_player": state.current_player, "last_roll": state.last_roll,
            "status": state.status, "updated_at": datetime.now(timezone.utc),
        }})
        doc.update({"players": [{"color": p.color, "tokens": p.tokens} for p in state.players],
                    "current_player": state.current_player, "last_roll": state.last_roll,
                    "status": state.status})
        return game_payload(doc, message)
    if kind == "move":
        if state.current_player != 0 or state.last_roll is None:
            return game_payload(doc, "Roll the dice first.")
        token = action.get("token")
        if type(token) is not int or token not in legal_moves(state.players[0], state.last_roll):
            return game_payload(doc, "That token cannot move. Select a highlighted token.")
        dice = state.last_roll
        captured = move_token(state, 0, token, dice)
        if state.status == "finished":
            message = "🏆 Victory! You brought all four tokens home."
            await database.db.users.update_one({"telegram_id": user_id}, {"$inc": {"wins": 1, "xp": 100}})
        else:
            next_turn(state, dice)
            message = f"You moved token {token + 1}."
            if captured:
                message += " You captured an AI token!"
            if state.current_player == 1:
                ai_dice = secrets.randbelow(6) + 1
                message += " " + await play_ai_turn(state, ai_dice)
        await database.db.games.update_one({"_id": doc["_id"]}, {"$set": {
            "players": [{"color": p.color, "tokens": p.tokens} for p in state.players],
            "current_player": state.current_player, "last_roll": state.last_roll,
            "status": state.status, "updated_at": datetime.now(timezone.utc),
        }})
        doc.update({"players": [{"color": p.color, "tokens": p.tokens} for p in state.players],
                    "current_player": state.current_player, "last_roll": state.last_roll,
                    "status": state.status})
        return game_payload(doc, message)
    return game_payload(doc, "Unknown game action.")


async def handle_message(message: dict):
    chat = message.get("chat", {})
    sender = message.get("from", {})
    text = (message.get("text") or "").strip()
    if chat.get("type") != "private" or not sender:
        return
    user = await register_user(sender)
    if text.startswith("/start"):
        try:
            await send_home_widget(chat["id"], user)
        except Exception:
            log.exception("Could not send Ludo Arena widget to chat %s", chat["id"])
            await bot.send_message(chat["id"],
                "👑 Welcome to Ludo Arena!\nYour game menu is being prepared. Please try /start again shortly.")
    elif text.startswith("/help"):
        await bot.send_message(chat["id"], "🎲 Ludo Arena\n/start — Open the royal game menu\n/help — Show help")
    else:
        await bot.send_message(chat["id"], "👑 Open your Ludo Arena menu with /start.")


async def handle_widget_query(query: dict):
    query_id = query.get("id")
    viewer = query.get("from", {})
    raw = query.get("data", "")
    try:
        payload = json.loads(raw) if raw.startswith("{") else {"action": raw}
    except (TypeError, json.JSONDecodeError):
        payload = {"action": ""}
    action = payload.get("action", "")
    user_id = viewer.get("id")
    if not user_id:
        await call("answerWidgetQuery", {"widget_query_id": query_id, "data": json.dumps({"screen": "home", "message": "Unable to identify player."})})
        return
    if action in {"solo", "roll", "move"}:
        result = await widget_game_action(user_id, payload)
    else:
        labels = {
            "play": "Choose Solo Challenge to start a match.",
            "friends": "Private rooms arrive in Phase 3.",
            "random": "Quick Match arrives in Phase 3.",
            "profile": "Profile panel is coming soon.",
            "ranks": "Leaderboards arrive in Phase 5.",
            "settings": "Settings panel is coming soon.",
            "rewards": "Daily rewards arrive in Phase 4.",
            "help": "Bring a token out with a six. Reach home with an exact roll. Safe squares protect tokens.",
            "home": "You are already on Home.",
        }
        result = {"screen": "home", "message": labels.get(action, "This feature will be enabled in a later phase.")}
        await database.db.widget_actions.insert_one({
            "telegram_id": user_id, "action": action,
            "created_at": datetime.now(timezone.utc),
        })
    await call("answerWidgetQuery", {"widget_query_id": query_id, "data": json.dumps(result, separators=(",", ":"))})


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    if settings.webhook_secret:
        supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not secrets.compare_digest(supplied, settings.webhook_secret):
            raise HTTPException(status_code=403, detail="Invalid webhook secret")
    update = await request.json()
    try:
        if "message" in update:
            await handle_message(update["message"])
        elif "widget_query" in update:
            await handle_widget_query(update["widget_query"])
    except Exception:
        log.exception("Failed to process Telegram update %s", update.get("update_id"))
    return JSONResponse({"ok": True})
