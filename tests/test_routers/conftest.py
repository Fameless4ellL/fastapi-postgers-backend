from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm.session import Session
from models.other import Currency, Game, GameType, Network, Ticket, GameView
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
    user = db.query(User).filter(
        User.username == "test_user1"
    ).first()

    if not user:
        hashed_password = get_password_hash("test_password")
        user = User(
            phone_number="77079898911",
            username="test_user1",
            password=hashed_password,
            country="KAZ",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    yield user

    try:
        db.query(User).filter(
            User.id == user.id
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
    network = db.query(Network).filter(
        Network.symbol == "TST"
    ).first()

    if not network:
        network = Network(
            name="Test Network",
            symbol="TST",
            chain_id=1,
            rpc_url="http://localhost:8545",
            explorer_url="http://localhost:8080",
        )
        db.add(network)
        db.commit()
        db.refresh(network)

    yield network
    try:
        db.query(Network).filter(
            Network.id == network.id
        ).delete()
        db.commit()
    except Exception as e:
        db.rollback()
        print(e)


@pytest.fixture
def currency(db: Session, network: Network):
    currency = db.query(Currency).filter(
        Currency.code == "TST"
    ).first()

    if not currency:
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
        db.refresh(currency)

    yield currency

    try:
        db.query(Currency).filter(
            Currency.id == currency.id
        ).delete()
        db.commit()
    except Exception as e:
        db.rollback()
        print(e)


@pytest.fixture(params=GameView)
def game_view(
    request: pytest.FixtureRequest
):
    yield request.param, "YourMom"


@pytest.fixture(params=GameType)
def game(
    db: Session,
    currency: Currency,
    request: pytest.FixtureRequest,
    game_view: GameView
):
    view, prize = game_view

    db.query(Game).filter(
        Game.name == "Test Game"
    ).delete()
    db.commit()

    game = Game(
        name="Test Game",
        currency_id=currency.id,
        game_type=request.param,
        kind=view,
        prize=prize,
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
def ticket(
    db: Session,
    user: User,
    game: Game
):
    db.query(Ticket).filter(
        Ticket.user_id == user.id
    ).delete()
    db.commit()

    _ticket = Ticket(
        user_id=user.id,
        game_id=game.id,
        numbers=[1, 2, 3, 4, 5],
        amount=1
    )
    db.add(_ticket)
    db.commit()

    yield _ticket

    try:
        db.query(Ticket).filter(
            Ticket.user_id == user.id
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
