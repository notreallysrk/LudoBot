import httpx
from app.config import settings

API = f"https://api.telegram.org/bot{settings.bot_token}/"


async def call(method: str, payload: dict):
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(API + method, json=payload)

        # Parse Telegram's JSON error before raising so logs include its description.
        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise RuntimeError(f"Telegram {method} returned a non-JSON response")

        if not response.is_success or not data.get("ok"):
            error_code = data.get("error_code", response.status_code)
            description = data.get("description", response.reason_phrase)
            raise RuntimeError(
                f"Telegram {method} failed ({error_code}): {description}"
            )

        return data["result"]
