"""User exceptions."""

import typing as t
from uuid import UUID
from pydantic import BaseModel
from src.exceptions.base import NotFoundError, ForbiddenError
from src.exceptions.constants.user import (
    USER_NOT_FOUND,
    USER_IS_BLOCKED
)


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
