import httpx
from app.config import settings

API = f"https://api.telegram.org/bot{settings.bot_token}/"

async def call(method: str, payload: dict):
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(API + method, json=payload)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {data}")
        return data["result"]
