from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

_client: Optional[AsyncIOMotorClient] = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_uri)
    return _client


def get_database() -> AsyncIOMotorDatabase:
    """FastAPI dependency: trả về handle DB dùng chung."""
    return get_client()[settings.mongo_db]


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
