from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm.session import Session
from models.other import Currency, Game, GameType, Network
from models.user import User, Balance
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
    db.query(User).filter(
        User.username == "test_user1"
    ).delete()
    db.commit()

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

    try:
        db.query(User).filter(
            User.username == "test_user1"
        ).delete()
        db.commit()
    except Exception as e:
        db.rollback()
        print(e)


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
def network(db: Session):
    db.query(Currency).filter(
        Currency.network_id == db.query(Network.id).filter(Network.name == "Test Network").scalar()
    ).delete()
    db.commit()

    db.query(Network).filter(
        Network.name == "Test Network"
    ).delete()
    db.commit()

    network = Network(
        name="Test Network",
        symbol="TST",
        chain_id=1,
        rpc_url="http://localhost:8545",
        explorer_url="http://localhost:8080",
    )
    db.add(network)
    db.commit()

    yield network

    db.query(Currency).filter(
        Currency.network_id == db.query(Network.id).filter(Network.name == "Test Network").scalar()
    ).delete()
    db.commit()

    db.query(Network).filter(
        Network.name == "Test Network"
    ).delete()
    db.commit()


@pytest.fixture
def currency(db: Session, network: Network):
    currency = Currency(
        code="TST",
        name="Test Currency",
        network_id=network.id,
        address="0x",
        decimals=18,
        conversion_rate=1
    )
    db.add(currency)
    db.commit()

    yield currency


@pytest.fixture(params=GameType)
def game(
    db: Session,
    currency: Currency,
    request: pytest.FixtureRequest
):
    db.query(Game).filter(
        Game.name == "Test Game"
    ).delete()
    db.commit()

    game = Game(
        name="Test Game",
        currency_id=currency.id,
        game_type=request.param,
        scheduled_datetime="2025-01-30T12:57:40",
    )
    db.add(game)
    db.commit()

    yield game

    try:
        db.query(Game).filter(
            Game.name == "Test Game"
        ).delete()
        db.commit()
    except Exception as e:
        db.rollback()
        print(e)


@pytest.fixture
def balance(db: Session, user: User):

    balance = Balance(
        user_id=user.id,
        currency_id=1,
        balance=0
    )
    db.add(balance)
    db.commit()

    yield balance

    db.query(Balance).filter(
        Balance.user_id == user.id
    ).delete()
    db.commit()
