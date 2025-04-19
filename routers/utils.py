from dataclasses import dataclass
import traceback
from itertools import islice
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Annotated, Any
import uuid
from aiohttp import client_exceptions
from fastapi import Depends, HTTPException, status, security
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta
from sqlalchemy import select
from models.db import get_db, get_sync_db
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User, Role
from web3 import Web3, middleware
from models.other import Game, GameStatus, GameType, Network, Currency
import settings
from utils.signature import decode_access_token
from settings import email, settings
from globals import aredis, q
from utils.web3 import AWSHTTPProvider
from utils.workers import worker


oauth2_scheme = security.OAuth2PasswordBearer(tokenUrl="/v1/token")
admin_oauth2_scheme = security.OAuth2PasswordBearer(
    tokenUrl="/v1/token",
    scopes={
        Role.GLOBAL_ADMIN.value: "Global admin",
        Role.ADMIN.value: "Admin",
        Role.LOCAL_ADMIN.value: "Local admin",
        Role.SUPER_ADMIN.value: "Super admin",
        Role.FINANCIER.value: "Financier",
        Role.SMM.value: "SMM",
        Role.SUPPORT.value: "Support",
    }
)

invalid_token = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid token",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass(frozen=True)
class Token:
    id: int
    username: str = None
    country: str = None
    scopes: list[str] = None
    exp: datetime = None


async def get_user_token(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> Token:
    payload = decode_access_token(token)
    try:
        _token = Token(**payload)
    except TypeError:
        raise invalid_token

    if payload is None:
        raise invalid_token

    # if not await aredis.exists(f"TOKEN:USERS:{_token.id}"):
    #     raise invalid_token

    # session = await aredis.get(f"TOKEN:USERS:{_token.id}")

    # if token != session.decode("utf-8"):
    #     raise invalid_token

    return _token


async def get_user(
    token: Annotated[Token, Depends(get_user_token)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    user = await db.execute(
        select(User).filter(User.id == token.id)
    )
    user = user.scalar()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    return user


async def get_admin_token(
    token: Annotated[str, Depends(admin_oauth2_scheme)],
    security_scopes: security.SecurityScopes
) -> Token:
    payload = decode_access_token(token)

    try:
        _token = Token(**payload)
    except TypeError:
        raise invalid_token

    if payload is None:
        raise invalid_token

    if not _token.scopes:
        raise invalid_token

    for scope in _token.scopes:
        if scope not in security_scopes.scopes:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not enough permissions"
            )

    if not await aredis.exists(f"TOKEN:ADMINS:{_token.id}"):
        raise invalid_token

    session = await aredis.get(f"TOKEN:ADMINS:{_token.id}")

    if token != session.decode("utf-8"):
        raise invalid_token

    return _token


async def get_admin(
    token: Annotated[Token, Depends(get_admin_token)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    user = await db.execute(select(User).filter(
        User.id == token.id,
        User.role != Role.USER.value
    ))
    user = user.scalar()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    return user


async def get_network(
    db: Annotated[AsyncSession, Depends(get_db)],
    network: str = "ETH"
) -> Network:
    net = await db.execute(select(Network).filter(Network.symbol == network))
    net = net.scalar()

    if net is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Network not found"
        )

    return net


async def get_currency(
    db: Annotated[AsyncSession, Depends(get_db)],
    network: Annotated[Network, Depends(get_network)],
    currency: str = "USDT"
) -> Currency:
    cur = await db.execute(select(Currency).filter(
        Currency.code == currency,
        Currency.network_id == network.id
    ))
    cur = cur.scalar()

    if cur is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Currency not found"
        )

    return cur


def get_currency_by_id(
    currency_id: int
) -> Currency:
    db = next(get_sync_db())
    cur = db.execute(select(Currency).filter(Currency.id == currency_id))
    cur = cur.scalar()

    if cur is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Currency not found"
        )

    return cur.id


def get_first_currency() -> Currency:
    db = next(get_sync_db())
    cur = db.query(Currency).first()

    if cur is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Currency not found"
        )

    return cur.id


async def get_w3(
    network: Annotated[Network, Depends(get_network)],
) -> Web3:
    try:
        w3 = Web3(AWSHTTPProvider(network.rpc_url))
        if not w3.is_connected():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Network is not connected"
            )
    except client_exceptions.ClientError:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Network is not available"
        )

    acct = w3.eth.account.from_key(settings.private_key)

    w3.middleware_onion.inject(middleware.SignAndSendRawMiddlewareBuilder.build(acct), layer=0)
    w3.eth.default_account = acct.address

    return w3


async def generate_game(
    db: AsyncSession, _type: GameType = GameType.GLOBAL, country: str = None
):
    """
    creating a new game instance based on Game
    """
    game = await db.execute(
        select(Game).filter(
            Game.repeat.is_(True),
            Game.status == GameStatus.PENDING,
            Game.game_type == _type,
            Game.country == country
        )
    )
    game = game.scalars().first()

    if not game:
        currency = await db.execute(
            select(Currency)
        )
        currency = currency.scalar()

        game = Game(
            name=f"game #{str(uuid.uuid4())}",
            game_type=_type,
            currency_id=currency.id,
            description="Default game",
            country=country,
            repeat=True,
            repeat_days=[0, 1, 2, 3, 4, 5, 6],
            scheduled_datetime=datetime.now() + timedelta(days=1),
        )

        db.add(game)
        await db.commit()
        await db.refresh(game)

    stmt = select(Game).filter(
        Game.id == game.id
    ).options(
        joinedload(Game.currency)
    )
    game = await db.execute(stmt)
    game = game.scalar()

    q.enqueue_at(
        game.scheduled_datetime,
        getattr(worker, f"proceed_game"),
        game.id,
        job_id=f"proceed_game_{game.id}",
    )

    return game


def nth(iterable, n, default=None):
    "Returns the nth item or a default value."
    return next(islice(iterable, n, None), default)


def url_for(name: str, **path_params: Any) -> str:
    """
    Generate a URL for the given endpoint name and path parameters.
    """
    return f"{settings.back_url}/{name}/" + "/".join(
        str(value) for value in path_params.values()
    )


def send_mail(
    subject: str,
    body: str,
    to_email: str,
):
    msg = MIMEMultipart()
    msg["From"] = email._from
    msg["To"] = to_email
    msg["subject"] = subject
    msg.attach(MIMEText(body))

    try:
        server = smtplib.SMTP(email.host, email.port)
        server.starttls()

        server.login(email.login, email.password)

        text = msg.as_string()

        server.sendmail(email._from, to_email, text)

        server.quit()
    except smtplib.SMTPException:
        traceback.print_exc()
