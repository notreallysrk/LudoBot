from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

client: AsyncIOMotorClient | None = None
db = None

async def connect_db():
    global client, db
    client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=10000)
    await client.admin.command("ping")
    db = client[settings.mongodb_db]
    await db.users.create_index("telegram_id", unique=True)
    await db.users.create_index("username")
    await db.widget_actions.create_index("created_at", expireAfterSeconds=60 * 60 * 24 * 30)
    await db.games.create_index([("telegram_id", 1), ("status", 1), ("updated_at", -1)])

async def close_db():
    global client
    if client:
        client.close()
        client = None
