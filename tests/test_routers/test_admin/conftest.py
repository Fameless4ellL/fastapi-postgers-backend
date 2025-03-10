from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm.session import Session
from models.other import Game, GameType
from models.user import Role, User, Balance
from globals import redis
from utils.signature import get_password_hash


PASSWORD = "test_password"


@pytest.fixture
def tear_down(db: Session):
    redis.set("SMS:testclient", 123456)
    yield
    redis.delete("SMS:testclient")

    db.query(User).filter(
        User.username == "testuser"
    ).delete()
    db.commit()


@pytest.fixture
def admin(
    db: Session,
    user: User,
):
    user.role = Role.SUPER_ADMIN.value
    db.commit()
    yield user


@pytest.fixture
def admin_token(
    api: TestClient,
    admin: User,
):
    response = api.post(
        "/v1/admin/login",
        json={
            "login": admin.username,
            "password": PASSWORD,
        }
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    yield response.json()["access_token"]
