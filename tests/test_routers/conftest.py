from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm.session import Session
from models.other import Game, GameType
from models.user import User
from globals import redis
from utils.signature import get_password_hash


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
def user(db: Session):
    hashed_password = get_password_hash("test_password")
    user = User(
        phone_number="+77079898911",
        username="test_user1",
        password=hashed_password,
        country="KZ",
    )
    db.add(user)
    db.commit()

    yield user

    db.query(User).filter(
        User.username == "test_user1"
    ).delete()
    db.commit()


@pytest.fixture
def token(
    db: Session,
    api: TestClient,
    user: User,
    tear_down: None
):
    response = api.post(
        "/v1/login",
        json={
            "username": user.username,
            "phone_number": user.phone_number,
            "code": "123456",
        }
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    yield response.json()["access_token"]



@pytest.fixture
def game(db: Session):
    game = Game(
        name="Test Game",
        game_type=GameType.GLOBAL,
        scheduled_datetime="2025-01-30T12:57:40",
    )
    db.add(game)
    db.commit()

    yield game

    db.query(Game).filter(
        Game.name == "Test Game"
    ).delete()
    db.commit()
