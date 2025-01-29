import pytest
from fastapi.testclient import TestClient
from models.db import get_sync_db
from asgi import fastapp
from sqlalchemy.orm.session import Session
from models.user import User
from globals import redis


@pytest.fixture(scope="class")
def api():
    with TestClient(
        fastapp, base_url="http://api:8100",
        backend_options={"use_uvloop": True},
    ) as client:
        yield client


@pytest.fixture(name="db")
def database():
    db = next(get_sync_db())
    yield db
    db.close()
