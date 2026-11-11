from pathlib import Path

WIDGET_HTML = (Path(__file__).resolve().parent.parent / "widget" / "home.html").read_text(encoding="utf-8")

async def send_home_widget(chat_id: int, user: dict):
    # Widget source is fixed at send time. User-specific values are sent as chat_data.
    import json
    state = {
        "name": user.get("first_name") or "Player",
        "coins": int(user.get("coins", 0)),
        "wins": int(user.get("wins", 0)),
        "level": int(user.get("level", 1)),
    }
    from app.telegram_api import call
    return await call("sendWidget", {
        "chat_id": chat_id,
        "html": WIDGET_HTML,
        "allow_queries": True,
        "chat_data": json.dumps(state, separators=(",", ":")),
        "caption": "👑 LUDO ARENA • Your arena. Your victory.",
    })
