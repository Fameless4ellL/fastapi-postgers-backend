"""User exceptions."""

import typing as t
from uuid import UUID
from pydantic import BaseModel
from src.exceptions.base import NotFoundError
from src.exceptions.constants.user import (
    USER_NOT_FOUND,
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
