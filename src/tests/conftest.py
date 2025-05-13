import asyncio
import os
from typing import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from redis.asyncio import Redis

from src.asgi import fastapp
from src.models.db import get_db
from settings import settings


@pytest.fixture(scope="session")
def api() -> TestClient:
    with TestClient(
        fastapp, base_url="http://api:8100",
        backend_options={"use_uvloop": True},
    ) as client:
        yield client


@pytest.fixture(scope="session")
async def async_api() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=fastapp), base_url="http://api:8100") as client:
        yield client


@pytest.fixture(name="db")
async def database() -> AsyncGenerator:
    async for session in get_db():
        yield session


@pytest.fixture(name="aredis")
async def _aredis() -> AsyncGenerator[Redis, None]:
    redis = Redis(
        host=os.environ.get("REDIS_HOST", "redis"),
    )
    try:
        yield redis
    finally:
        await redis.aclose()


# TODO: refactor Deprecated
@pytest.fixture(scope="session")
def event_loop():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True, scope="session")
@pytest.mark.skipif(
    not settings.debug,
    reason="This test is only for debug mode",
)
@pytest.mark.no_cover
async def is_debug():
    """
    This fixture is used to skip tests if the debug mode is not enabled.
    It is marked as autouse, so it will be applied to all tests in the session.
    """
    if not settings.debug:
        pytest.skip("Skipping test because debug mode is not enabled.")
