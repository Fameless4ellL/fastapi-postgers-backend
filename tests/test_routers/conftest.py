import pytest
from sqlalchemy.orm.session import Session
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
