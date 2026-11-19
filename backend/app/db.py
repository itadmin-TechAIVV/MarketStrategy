"""MongoDB access (pymongo async client). Every tenant-owned collection carries
`organization_id`, and every compound index starts with it."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pymongo import ASCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from .config import get_settings

_client: AsyncMongoClient | None = None


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_db() -> AsyncDatabase:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncMongoClient(settings.mongo_uri.get_secret_value(), tz_aware=True)
    return _client[get_settings().mongo_db]


async def ensure_indexes() -> None:
    db = get_db()
    await db.users.create_index([("email", ASCENDING)], unique=True)
    await db.users.create_index([("organization_id", ASCENDING)])
    await db.workspaces.create_index([("organization_id", ASCENDING), ("updated_at", ASCENDING)])
    await db.sources.create_index([("organization_id", ASCENDING), ("workspace_id", ASCENDING), ("url", ASCENDING)])
    await db.messages.create_index(
        [("organization_id", ASCENDING), ("workspace_id", ASCENDING), ("seq", ASCENDING)], unique=True
    )
    await db.strategy_sections.create_index(
        [("organization_id", ASCENDING), ("workspace_id", ASCENDING), ("key", ASCENDING)], unique=True
    )
    await db.section_versions.create_index(
        [("organization_id", ASCENDING), ("workspace_id", ASCENDING), ("key", ASCENDING), ("version", ASCENDING)]
    )


async def close() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
