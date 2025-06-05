"""Jackpot exceptions."""

import typing as t
from datetime import datetime, timezone
from uuid import UUID
from pydantic import BaseModel
from src.exceptions.base import NotFoundError
from src.exceptions.constants.jackpot import (
    JACKPOT_NOT_FOUND,
    JACKPOT_ALREADY_STARTED
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

    @staticmethod
    async def raise_exception_jackpot_already_started(
        game: t.Union[None, UUID, BaseModel, list[BaseModel]],
    ) -> bool:
        """Raise exception if arbitrator not found."""
        if game.fund_start > datetime.now(timezone.utc):
            raise NotFoundError(name=JACKPOT_ALREADY_STARTED)
        return True
