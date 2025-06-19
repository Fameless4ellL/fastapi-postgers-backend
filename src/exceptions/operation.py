"""BalanceChangehistory exceptions."""

import typing as t
from uuid import UUID
from pydantic import BaseModel
from rq.job import Job

from src.exceptions.base import NotFoundError
from src.exceptions.constants.transactions import (
    OPERATION_NOT_FOUND,
    OPERATION_IS_FINISHED
)


class HistoryExceptions:
    """BalanceChangehistory exceptions class."""
    @staticmethod
    async def operation_not_found(
        obj: t.Union[None, UUID, BaseModel, list[BaseModel]],
    ) -> bool:
        """Raise exception if BalanceChangehistory not found."""
        if not obj:
            raise NotFoundError(name=OPERATION_NOT_FOUND)
        return True

    @staticmethod
    async def operation_is_finished(
        obj: Job,
    ) -> bool:
        """Raise exception if BalanceChangehistory is finished."""
        if obj.is_finished:
            raise NotFoundError(name=OPERATION_IS_FINISHED)
        return True
