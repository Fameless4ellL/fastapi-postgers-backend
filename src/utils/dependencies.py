import logging
import smtplib
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from itertools import islice
from typing import Annotated

import pytz
import requests
from aiohttp import client_exceptions
from fastapi import Depends, HTTPException, status, security, Request, Header
from httpx import AsyncClient
from pytz.tzinfo import DstTzInfo
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from web3 import Web3, middleware

from settings import email, settings
from src.globals import aredis, q
from src.models.db import get_db
from src.models.other import Game, GameStatus, GameType, Network, Currency
from src.models.user import User, Role
from src.utils import worker
from src.utils.signature import decode_access_token
from src.utils.web3 import AWSHTTPProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


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


async def http_client(request: Request) -> AsyncClient:
    return request.state.client


async def get_ip(
    request: Request,
    x_forwarded_for: str = Header(None, include_in_schema=False, alias="X-Forwarded-For"),
    x_real_ip: str = Header(None, include_in_schema=False, alias="X-Real-IP"),
) -> str:
    return x_forwarded_for or x_real_ip or request.client.host


async def get_timezone(
    ip: Annotated[str, Depends(get_ip)],
    client: Annotated[AsyncClient, Depends(http_client)]
) -> DstTzInfo:
    """
    Get timezone by ip
    """
    cached = await aredis.get(f"TZ:{ip}")
    if cached:
        return pytz.timezone(cached.decode("utf-8"))

    try:
        response = await client.get(
            f"http://ip-api.com/json/{ip}?fields=timezone"
        )
        response.raise_for_status()
        data = response.json()
        result = data["timezone"]
    except (requests.RequestException, KeyError):
        traceback.print_exc()
        result = "UTC"

    await aredis.set(f"TZ:{ip}", result, ex=60*5)
    return pytz.timezone(result)


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
        worker.proceed_game,
        game_id=game.id,
        job_id=f"proceed_game_{game.id}",
    )

    return game


def nth(iterable, n, default=None):
    "Returns the nth item or a default value."
    return next(islice(iterable, n, None), default)


def send_mail(
    subject: str,
    body: str,
    to_email: str,
):
    msg = MIMEMultipart()
    msg["From"] = email.FROM
    msg["To"] = to_email
    msg["subject"] = subject
    msg.attach(MIMEText(body))

    try:
        logger.info(f"Connecting to SMTP server: {email.host}:{email.port}")
        server = smtplib.SMTP(email.host, email.port)
        server.starttls()

        logger.info("Logging in to SMTP server")
        server.login(email.login, email.password)

        text = msg.as_string()
        logger.info(f"Sending email to {to_email}")
        server.sendmail(email.FROM, to_email, text)

        server.quit()
        logger.info("Email sent successfully")
    except smtplib.SMTPException as e:
        logger.error(f"Failed to send email: {e}")
        traceback.print_exc()


async def is_field_unique(
    db: AsyncSession,
    table: object,
    field_name: str,
    field_value: str,
    exclude_id: int = None
) -> bool:
    """
    Check if a field value is unique in the table.

    :param db: AsyncSession instance
    :param table: The SQLAlchemy table to check (e.g., User)
    :param field_name: The name of the field to check (e.g., 'email')
    :param field_value: The value of the field to check
    :param exclude_id: Optional ID to exclude from the check (useful for updates)
    :return: True if unique, False otherwise
    """
    if exclude_id:
        stmt = select(
            exists().where(
                getattr(table, field_name) == field_value,
                getattr(table, 'id') != exclude_id
            )
        )
    else:
        stmt = select(
            exists().where(
                getattr(table, field_name) == field_value,
            )
        )

    result = await db.execute(stmt)
    return not result.scalar()


async def transaction_atomic(db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Context manager for handling transactions in an async session.
    """
    async with db.begin():
        yield db
