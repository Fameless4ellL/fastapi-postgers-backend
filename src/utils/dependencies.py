import logging
import traceback
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import islice
from typing import Annotated, Optional
from typing import Type

import pytz
import requests
from aiohttp import client_exceptions
from fastapi import Depends, status, security, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from httpx import AsyncClient
from pytz.tzinfo import DstTzInfo
from sqlalchemy import select, exists, func
from sqlalchemy.ext.asyncio import AsyncSession
from web3 import Web3, middleware

from settings import settings
from src.exceptions.api import ApiException
from src.exceptions.base import UnauthorizedError, ForbiddenError
from src.exceptions.constants.auth import (
    PERMISSION_DENIED,
    NO_SCOPE,
    BAD_TOKEN,
    TOKEN_NOT_FOUND,
    INVALID_AUTH,
    INVALID_SCHEME
)
from src.exceptions.currency import CurrencyExceptions
from src.exceptions.limit import LimitExceptions
from src.exceptions.network import NetworkExceptions
from src.exceptions.user import UserExceptions
from src.globals import aredis
from src.models import Limit, OperationType, LimitType
from src.models.db import get_db
from src.models.other import Network, Currency
from src.models.user import User, Role, BalanceChangeHistory
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


@dataclass(frozen=True)
class Token:
    id: int
    username: Optional[str] = None
    country: Optional[str] = None
    scopes: Optional[list[str]] = None
    exp: Optional[datetime] = None


class JWTBearer(HTTPBearer):
    redis_key: str = "TOKEN:USERS:{id}"

    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request):
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)
        if not credentials:
            raise UnauthorizedError(INVALID_AUTH)

        if str(credentials.scheme).lower() != "bearer":
            raise UnauthorizedError(INVALID_SCHEME)

        return await self.verify(credentials.credentials)

    @staticmethod
    def get_token(token: str) -> Token:
        try:
            payload = Token(**decode_access_token(token))
        except TypeError:
            payload = None

        return payload

    async def verify(self, token: str) -> Token:
        """
        Verifies the validity of a session token using Redis.

        This method checks whether a given token exists and matches the expected value
        stored in Redis for the user's session. If the token is missing or invalid,
        it raises an UnauthorizedError.

        Args:
            token (str): The JWT or session token to be validated.

        Returns:
            Token: The decoded token payload object upon successful validation.

        Raises:
            UnauthorizedError: If the token is not found or does not match the session in Redis.
        """
        payload = self.get_token(token)

        if not await aredis.exists(self.redis_key.format(id=payload.id)):
            raise UnauthorizedError(TOKEN_NOT_FOUND)

        session = await aredis.get(self.redis_key.format(id=payload.id))

        if token != session.decode("utf-8"):
            raise UnauthorizedError(BAD_TOKEN)

        return payload


class JWTBearerAdmin(JWTBearer):
    redis_key: str = "TOKEN:ADMINS:{id}"

    async def verify(self, token: str) -> Token:
        payload = await super().verify(token)

        if not payload.scopes:
            raise UnauthorizedError(NO_SCOPE)

        return payload


async def get_user(
    token: Annotated[Token, Depends(JWTBearer())],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    user = await db.execute(
        select(User).filter(User.id == token.id)
    )
    user = user.scalar()
    await UserExceptions.raise_exception_user_not_found(user)
    await UserExceptions.user_is_blocked(user)
    return user


class BasePermission(ABC):
    exception = UnauthorizedError(PERMISSION_DENIED)

    @abstractmethod
    async def has_permission(self, request: Request) -> bool:
        """has permission"""


class IsAdmin(BasePermission):
    scope = Role.ADMIN.value

    async def has_permission(
        self,
        token: Token,
    ) -> bool:
        return self.scope in token.scopes


class IsNotUser(BasePermission):
    scope = Role.USER.value

    async def has_permission(
        self,
        token: Token,
    ) -> bool:
        return self.scope not in token.scopes


class IsSuper(IsAdmin):
    scope = Role.SUPER_ADMIN.value


class IsGlobal(IsAdmin):
    scope = Role.GLOBAL_ADMIN.value


class IsLocal(IsAdmin):
    scope = Role.LOCAL_ADMIN.value


class IsSmm(IsAdmin):
    scope = Role.SMM.value


class IsFinancier(IsAdmin):
    scope = Role.FINANCIER.value


class IsSupport(IsAdmin):
    scope = Role.SUPPORT.value


class IsAuthenticated(IsAdmin):
    scope = "auth"


class IsNotAuthenticated(IsNotUser):
    scope = "auth"


class Permission(JWTBearerAdmin):
    def __init__(
        self,
        permissions: list[Type[BasePermission]] = None
    ):
        super().__init__()
        self.permissions = permissions

        if not self.permissions:
            self.permissions = [IsNotUser, IsNotAuthenticated]

    async def __call__(self, request: Request):
        token = await super().__call__(request)

        err = None
        for permission in self.permissions:
            cls = permission()
            if await cls.has_permission(token):
                return

            err = cls.exception

        if err:
            raise err

        return token


async def get_admin_token(
    token: Annotated[Token, Depends(JWTBearerAdmin())],
    security_scopes: security.SecurityScopes
) -> Token:
    warnings.warn(
        (
            "get_admin_token() is deprecated and will be removed in a future release."
            " Use JWTBearerAdmin() instead."
        ),
        DeprecationWarning,
        stacklevel=2
    )
    for scope in token.scopes:
        if scope not in security_scopes.scopes:
            raise UnauthorizedError(PERMISSION_DENIED)

    return token


async def get_admin(
    token: Annotated[Token, Depends(JWTBearerAdmin())],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    user = await db.execute(select(User).filter(
        User.id == token.id,
        User.role != Role.USER.value
    ))
    user = user.scalar()
    await UserExceptions.raise_exception_user_not_found(user)
    return user


async def get_network(
    db: Annotated[AsyncSession, Depends(get_db)],
    network: str = "ETH"
) -> Network:
    net = await db.execute(select(Network).filter(Network.symbol == network))
    net = net.scalar()
    await NetworkExceptions.network_not_found(net)
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
    await CurrencyExceptions.currency_not_found(cur)
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
            f"http://ip-api.com/json/{ip}?fields=timezone",
            timeout=5
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
        await NetworkExceptions.network_is_not_connected(w3)
    except client_exceptions.ClientError as exc:
        traceback.print_exc()
        raise ApiException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            name="Network is not available"
        ) from exc

    acct = w3.eth.account.from_key(settings.private_key)

    w3.middleware_onion.inject(middleware.SignAndSendRawMiddlewareBuilder.build(acct), layer=0)
    w3.eth.default_account = acct.address

    return w3


def nth(iterable, n, default=None):
    """Returns the nth item or a default value."""
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


class LimitTypeBase(ABC):
    """
    Base class for limit types.
    """
    def __init__(
        self,
        user: User = None,
        db: AsyncSession = None,
        request: Request = None,
        limit: Limit = None
    ):
        self.user = user
        self.db = db
        self.request = request
        self.limit = limit

    @abstractmethod
    async def check(self):
        raise NotImplementedError("Subclasses should implement this method.")

    @abstractmethod
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
            await LimitExceptions.limit_type_is_not_supported(_limit)

            _limit = _limit(
                db=self.db,
                user=self.user,
                request=request,
                limit=limit,
            )
            _, err = await _limit.check()
            if err:
                raise ForbiddenError(err)

        return True

    async def _get_limits(self):
        """
        Fetch limits for the user based on their type and operation type.
        """
        stmt = select(Limit).filter(
            Limit.kyc == self.user.kyc,
            Limit.is_deleted.is_(False),
        )
        db = await self.db.execute(stmt)
        return db.scalars().all()
