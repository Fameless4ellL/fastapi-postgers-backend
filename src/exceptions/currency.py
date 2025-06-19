"""Currency exceptions."""

import typing as t
from uuid import UUID
from pydantic import BaseModel
from src.exceptions.base import NotFoundError
from src.exceptions.constants.currency import (
    CURRENCY_NOT_FOUND,
)


class CurrencyExceptions:
    """Currency exceptions class."""
    @staticmethod
    async def currency_not_found(
        obj: t.Union[None, UUID, BaseModel, list[BaseModel]],
    ) -> bool:
        """Raise exception if currency is not found."""
        if not obj:
            raise NotFoundError(name=CURRENCY_NOT_FOUND)
        return True
