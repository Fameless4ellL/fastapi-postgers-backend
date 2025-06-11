import logging
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import islice
from typing import Annotated, Optional

import pytz
import requests
from aiohttp import client_exceptions
from fastapi import Depends, HTTPException, status, security, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from httpx import AsyncClient
from pytz.tzinfo import DstTzInfo
from sqlalchemy import select, exists, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from web3 import Web3, middleware

from settings import settings
from src.globals import aredis, q
from src.models import Limit, LimitStatus, OperationType, LimitType
from src.models.db import get_db
from src.models.other import Game, GameStatus, GameType, Network, Currency
from src.models.user import User, Role, BalanceChangeHistory
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

invalid_token = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid token",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass(frozen=True)
class Token:
    id: int
    username: Optional[str] = None
    country: Optional[str] = None
    scopes: Optional[list[str]] = None
    exp: Optional[datetime] = None


class JWTBearer(HTTPBearer):
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request):
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)
        if not credentials:
            raise HTTPException(status_code=403, detail="Invalid authorization code.")

        if str(credentials.scheme).lower() != "bearer":
            raise HTTPException(status_code=403, detail="Invalid authentication scheme.")

        if not await self.verify(credentials.credentials):
            raise HTTPException(status_code=403, detail="Invalid token or expired token.")
        return self.get_token(credentials.credentials)

    @staticmethod
    def get_token(token: str) -> Token:
        try:
            payload = Token(**decode_access_token(token))
        except TypeError:
            payload = None

        return payload

    async def verify(self, token: str) -> bool:
        is_token_valid: bool = False

        payload = self.get_token(token)
        if payload:
            is_token_valid = True

        if not await aredis.exists(f"TOKEN:USERS:{payload.id}"):
            raise invalid_token

        session = await aredis.get(f"TOKEN:USERS:{payload.id}")

        if token != session.decode("utf-8"):
            raise invalid_token

        return is_token_valid


class JWTBearerAdmin(JWTBearer):
    async def verify(self, token: str) -> bool:
        is_token_valid: bool = False

        payload = JWTBearerAdmin.get_token(token)
        if payload:
            is_token_valid = True

        if not payload.scopes:
            raise invalid_token

        if not await aredis.exists(f"TOKEN:ADMINS:{payload.id}"):
            raise invalid_token

        session = await aredis.get(f"TOKEN:ADMINS:{payload.id}")

        if token != session.decode("utf-8"):
            raise invalid_token

        return is_token_valid


async def get_user_token(
    token: Annotated[Token, Depends(JWTBearer())],
) -> Token:
    return token


async def get_user(
    token: Annotated[Token, Depends(get_user_token)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    user = await db.execute(
        select(User).filter(User.id == token.id)
    )
    user = user.scalar()
    # TODO improve err raise
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    if user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is blocked"
        )

    return user


async def get_admin_token(
    token: Annotated[Token, Depends(JWTBearerAdmin())],
    security_scopes: security.SecurityScopes
) -> Token:
    for scope in token.scopes:
        if scope not in security_scopes.scopes:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not enough permissions"
            )

    return token


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


class LimitTypeBase:
    """
    Base class for limit types.
    """
    def __init__(self, user: User = None, db: AsyncSession = None, request: Request = None, limit: Limit = None):
        self.user = user
        self.db = db
        self.request = request
        self.limit = limit

    async def check(self):
        raise NotImplementedError("Subclasses should implement this method.")

    def clean(self, op: Decimal):
        raise NotImplementedError("Subclasses should implement this method.")


class LimitTypeSum(LimitTypeBase):
    """
    Limit type for sum operations.
    """
    async def get_requested_amount(self):
        data = await self.request.json()
        if "amount" in data:
            return Decimal(data["amount"])

        return Decimal(0)

    async def check(self):
        op = (
            select(func.sum(BalanceChangeHistory.change_amount).label("total"))
            .filter(BalanceChangeHistory.user_id == self.user.id)
        )

        if self.limit.period.label is not None:
            op = op.filter(BalanceChangeHistory.created_at >= datetime.now() - self.limit.period.label)

        if self.limit.operation_type != OperationType.ALL:
            op = op.filter(BalanceChangeHistory.change_type == self.limit.operation_type.value)

        op = await self.db.execute(op)
        op = op.scalar() or 0
        op = op + await self.get_requested_amount()

        clean = self.clean(op)
        return op, clean

    def clean(self, op):
        if op > self.limit.value:
            return f"Limit exceeded: {self.limit.value}"
        return ""


class LimitTypeNumber(LimitTypeBase):
    """
    Limit type for number of operations.
    """
    async def check(self):
        op = (
            select(func.count(BalanceChangeHistory.id).label("total"))
            .filter(BalanceChangeHistory.user_id == self.user.id)
        )

        if self.limit.period.label is not None:
            op = op.filter(BalanceChangeHistory.created_at >= datetime.now() - self.limit.period.label)

        if self.limit.operation_type != OperationType.ALL:
            op = op.filter(BalanceChangeHistory.change_type == self.limit.operation_type.value)

        op = await self.db.execute(op)
        op = op.scalar() or 0

        clean = self.clean(op)
        return op, clean

    def clean(self, op):
        if op >= self.limit.value:
            return "Limit of operations exceeded"
        return ""


class LimitVerifier:
    """
    A class to verify user limits for specific operations.
    like withdrawal, purchase, or any other operation defined in OperationType.
    """
    _handlers = {
        LimitType.SUM: LimitTypeSum,
        LimitType.NUMBER: LimitTypeNumber,
    }

    def __init__(self, operation_type: OperationType):
        self.operation_type = operation_type
        self.user = None
        self.db = None
        self.request = None

    async def __call__(
        self,
        db: Annotated[AsyncSession, Depends(get_db)],
        user: Annotated[User, Depends(get_user)],
        request: Request
    ):
        """
        Verify user limits.
        """
        self.db = db
        self.user = user
        self.request = request

        limits = await self._get_limits()

        for limit in limits:
            if limit.operation_type not in {self.operation_type, OperationType.ALL}:
                continue

            _limit = self._handlers.get(limit.type)
            if not _limit:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported limit type: {limit.type}"
                )

            _limit = _limit(
                db=self.db,
                user=self.user,
                request=request,
                limit=limit,
            )
            _, err = await _limit.check()
            if err:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=err
                )

        return True

    async def _get_limits(self):
        """
        Fetch limits for the user based on their type and operation type.
        """
        stmt = select(Limit).filter(
            Limit.kyc == self.user.kyc,
            Limit.status == LimitStatus.ACTIVE,
            Limit.is_deleted.is_(False),
        )
        db = await self.db.execute(stmt)
        return db.scalars().all()
