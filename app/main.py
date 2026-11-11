import json
import logging
import secrets
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from aiogram import Bot
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import connect_db, close_db, db
from app.menus import send_home_widget
from app.telegram_api import call

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("ludo_arena")
bot = Bot(token=settings.bot_token)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
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
    await close_db()

app = FastAPI(title="Ludo Arena API", version="1.0.0", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"ok": True, "service": "ludo-arena", "phase": 1}

async def register_user(tg_user: dict):
    now = datetime.now(timezone.utc)
    user = await db.users.find_one_and_update(
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

async def handle_message(message: dict):
    chat = message.get("chat", {})
    sender = message.get("from", {})
    text = (message.get("text") or "").strip()
    if chat.get("type") != "private" or not sender:
        return
    user = await register_user(sender)
    if text.startswith("/start"):
        await send_home_widget(chat["id"], user)
    elif text.startswith("/help"):
        await bot.send_message(chat["id"], "🎲 Ludo Arena\n/start — Open the royal game menu\n/help — Show help")
    else:
        await bot.send_message(chat["id"], "👑 Open your Ludo Arena menu with /start.")

async def handle_widget_query(query: dict):
    query_id = query.get("id")
    raw = query.get("data", "")
    viewer = query.get("from", {})
    action = raw[:64]
    # Acknowledge every query quickly. Phase 1 actions are UI navigation/demo actions;
    # game, wallet transfers and matchmaking are intentionally not enabled yet.
    labels = {
        "play": "🎲 Game engine arrives in Phase 2.",
        "solo": "🤖 AI matches arrive in Phase 2.",
        "friends": "👥 Private rooms arrive in Phase 3.",
        "random": "🌐 Random matchmaking arrives in Phase 3.",
        "profile": "👤 Your profile is being prepared.",
        "ranks": "🏆 Leaderboards arrive in Phase 5.",
        "settings": "⚙️ Settings panel is coming soon.",
        "rewards": "🎁 Daily rewards arrive in Phase 4.",
        "help": "📖 Ludo rules and help will be added with the game engine.",
        "home": "🏠 You are already on Home.",
    }
    if action not in labels:
        labels[action] = "This feature will be enabled in a later phase."
    await db.widget_actions.insert_one({
        "telegram_id": viewer.get("id"), "action": action,
        "created_at": datetime.now(timezone.utc),
    })
    await call("answerWidgetQuery", {"widget_query_id": query_id, "data": labels[action][:1024]})

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
        # Return 200 to avoid endless retries for a malformed/unsupported update.
    return JSONResponse({"ok": True})
