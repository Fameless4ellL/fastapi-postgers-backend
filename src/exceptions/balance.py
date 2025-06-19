"""Balance exceptions."""

import typing as t
from uuid import UUID
from pydantic import BaseModel
from src.exceptions.base import NotFoundError
from src.exceptions.constants.transactions import (
    BALANCE_NOT_FOUND,
)


class BalanceExceptions:
    """Balance exceptions class."""
    @staticmethod
    async def balance_not_found(
        obj: t.Union[None, UUID, BaseModel, list[BaseModel]],
    ) -> bool:
        """Raise exception if Balance is not found."""
        if not obj:
            raise NotFoundError(name=BALANCE_NOT_FOUND)
        return True
