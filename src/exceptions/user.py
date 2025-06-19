"""User exceptions."""

import typing as t
from uuid import UUID
from pydantic import BaseModel
from src.exceptions.base import NotFoundError, ForbiddenError, UnauthorizedError, BadRequestError
from src.exceptions.constants.user import (
    USER_NOT_FOUND,
    USER_IS_BLOCKED
)
from src.exceptions.constants.auth import (
    INVALID_PASSWORD, IDENTICAL_PASSWORD,
)
from src.utils import verify_password


class UserExceptions:
    """User exceptions class."""
    @staticmethod
    async def raise_exception_user_not_found(
        obj: t.Union[None, UUID, BaseModel, list[BaseModel]],
    ) -> bool:
        """Raise exception if user not found."""
        if not obj:
            raise NotFoundError(name=USER_NOT_FOUND)
        return True

    @staticmethod
    async def user_is_blocked(
            obj: t.Union[None, UUID, BaseModel, list[BaseModel]],
    ) -> bool:
        """Raise exception if user not found."""
        if obj.is_blocked:
            raise ForbiddenError(name=USER_IS_BLOCKED)
        return True

    @staticmethod
    async def wrong_password(obj: t.Union[None, UUID, BaseModel, list[BaseModel]], password: str) -> bool:
        if not verify_password(password, obj.password):
            raise UnauthorizedError(INVALID_PASSWORD)
        return True

    @staticmethod
    async def identical_password(obj: t.Union[None, UUID, BaseModel, list[BaseModel]], password: str) -> bool:
        if obj.password == password:
            raise UnauthorizedError(IDENTICAL_PASSWORD)
        return True

    @staticmethod
    async def totp_verified(obj: t.Union[None, UUID, BaseModel, list[BaseModel]]) -> bool:
        if obj.verified:
            raise BadRequestError(IDENTICAL_PASSWORD)
        return True
