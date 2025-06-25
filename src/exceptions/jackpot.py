"""Jackpot exceptions."""

import typing as t
from uuid import UUID
from pydantic import BaseModel
from src.exceptions.base import NotFoundError
from src.exceptions.constants.jackpot import (
    JACKPOT_NOT_FOUND,
)


class JackpotExceptions:
    """User exceptions class."""
    @staticmethod
    async def raise_exception_user_not_found(
        game: t.Union[None, UUID, BaseModel, list[BaseModel]],
    ) -> bool:
        """Raise exception if user not found."""
        if not game:
            raise NotFoundError(name=JACKPOT_NOT_FOUND)
        return True
