import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from models.db import get_sync_db
from asgi import fastapp


@pytest.fixture(scope="session")
def api():
    with TestClient(
        fastapp, base_url="http://api:8100",
        backend_options={"use_uvloop": True},
    ) as client:
        yield client


@pytest.fixture(scope="session")
async def async_api():
    async with AsyncClient(transport=ASGITransport(app=fastapp), base_url="http://api:8100") as client:
        yield client


@pytest.fixture(name="db")
def database():
    db = next(get_sync_db())
    yield db
    db.close()
