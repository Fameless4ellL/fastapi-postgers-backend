from datetime import datetime

import pytest
from sqlalchemy import select, delete
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from src.models.other import Currency, Game, GameType, Network, Ticket, GameView
from src.models.user import User, Balance
from src.utils.signature import get_password_hash


@pytest.fixture
async def tear_down(
    db: AsyncSession,
    aredis: Redis,
):
    # SMS:127.0.0.1 or SMS:testclient
    await aredis.set("SMS:127.0.0.1", 123456)
    yield
    await aredis.delete("SMS:127.0.0.1")

    try:
        await db.execute(
            delete(User).where(User.username == "test_user3")
        )
        await db.commit()
    except Exception as e:
        print(e)


@pytest.fixture(scope="function")
async def user(db: AsyncSession):
    stmt = select(User).filter(User.username == "test_user2")

    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        hashed_password = get_password_hash("test_password")
        user = User(
            phone_number="77079898912",
            username="test_user2",
            password=hashed_password,
            country="KAZ",
        )
        db.add(user)
        await db.commit()
        result = await db.execute(stmt)
        user = result.scalars().first()

    yield user

    try:
        await db.execute(
            delete(User).where(User.id == user.id)
        )
        await db.commit()
    except Exception as e:
        print(e)


@pytest.fixture
async def token(
    db: AsyncSession,
    async_api: AsyncClient,
    user: User,
    tear_down: None
):
    response = await async_api.post(
        "/v1/check_code",
        json={
            "phone_number": user.phone_number,
            "code": "123456",
        }
    )

    assert response.status_code == status.HTTP_200_OK

    response = await async_api.post(
        "/v1/login",
        json={
            "username": user.username,
            "phone_number": f"+{user.phone_number}",
        }
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    yield response.json()["access_token"]


@pytest.fixture
async def network(db: AsyncSession):
    result = await db.execute(
        select(Network).filter(Network.symbol == "TST")
    )
    network = result.scalars().first()

    if not network:
        network = Network(
            name="Test Network",
            symbol="TST",
            chain_id=1,
            rpc_url="http://localhost:8545",
            explorer_url="http://localhost:8080",
        )
        db.add(network)
        await db.commit()
        await db.refresh(network)

    yield network

    try:
        await db.execute(
            delete(Network).where(Network.id == network.id)
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(e)


@pytest.fixture
async def currency(db: AsyncSession, network: Network):
    result = await db.execute(
        select(Currency).filter(Currency.code == "TST")
    )
    currency = result.scalars().first()

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
        await db.commit()
        await db.refresh(currency)

    yield currency

    try:
        await db.execute(
            delete(Currency).where(Currency.id == currency.id)
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(e)


@pytest.fixture(params=GameView)
async def game_view(request: pytest.FixtureRequest):
    yield request.param, "YourMom"


@pytest.fixture(params=GameType)
async def game(
    db: AsyncSession,
    currency: Currency,
    request: pytest.FixtureRequest,
    game_view: GameView
):
    view, prize = game_view

    await db.execute(
        delete(Game).where(Game.name == "Test Game")
    )
    await db.commit()

    game = Game(
        name="Test Game",
        currency_id=currency.id,
        game_type=request.param,
        kind=view,
        prize=prize,
        scheduled_datetime=datetime.now(),
    )
    db.add(game)
    await db.commit()

    yield game

    try:
        await db.execute(
            delete(Game).where(Game.name == "Test Game")
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(e)


@pytest.fixture
async def ticket(
    db: AsyncSession,
    user: User,
    game: Game
):
    await db.execute(
        delete(Ticket).where(Ticket.user_id == user.id)
    )
    await db.commit()

    _ticket = Ticket(
        user_id=user.id,
        game_id=game.id,
        numbers=[1, 2, 3, 4, 5],
        amount=1
    )
    db.add(_ticket)
    await db.commit()

    yield _ticket

    try:
        await db.execute(
            delete(Ticket).where(Ticket.user_id == user.id)
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(e)


@pytest.fixture
async def balance(db: AsyncSession, user: User):
    balance = Balance(
        user_id=user.id,
        currency_id=1,
        balance=0
    )
    db.add(balance)
    await db.commit()

    yield balance

    try:
        await db.execute(
            delete(Balance).where(Balance.user_id == user.id)
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(e)