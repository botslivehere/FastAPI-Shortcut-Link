import os
import sys

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///tests/test.db"
os.environ["SECRET_KEY"] = "test-secret-12345"
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
sys.path.insert(0, "api")

import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
import db as db_module
import links as links_module
from db import Base
from main import app

@pytest_asyncio.fixture
async def client():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)

    async with db_module.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    with patch.object(links_module, "redis_client", redis):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as ac:
            async with db_module.engine.begin() as conn:
                for t in reversed(Base.metadata.sorted_tables):
                    await conn.execute(t.delete())
            yield ac, redis

@pytest_asyncio.fixture
async def auth_client(client):
    ac, redis = client
    await ac.post("/register", json={"username": "test", "password": "pass12345"})
    r = await ac.post("/login", json={"username": "test", "password": "pass12345"})
    token = r.json()["access_token"]
    return ac, redis, {"Authorization": f"Bearer {token}"}
