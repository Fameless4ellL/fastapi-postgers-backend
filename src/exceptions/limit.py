"""Limit exceptions."""

import typing as t
from uuid import UUID
from pydantic import BaseModel
from src.exceptions.base import NotFoundError, BadRequestError
from src.exceptions.constants.limit import (
    LIMIT_NOT_FOUND,
    LIMIT_TYPE_IS_NOT_SUPPORTED
)


class LimitExceptions:
    """Limit exceptions class."""
    @staticmethod
    async def limit_not_found(
        obj: t.Union[None, UUID, BaseModel, list[BaseModel]],
    ) -> bool:
        """Raise exception if limit is not found."""
        if not obj:
            raise NotFoundError(name=LIMIT_NOT_FOUND)
        return True

    @staticmethod
    async def limit_is_deleted(
            obj: t.Union[None, UUID, BaseModel, list[BaseModel]],
    ) -> bool:
        """Raise exception if limit is deleted."""
        if not obj:
            raise BadRequestError(name=LIMIT_NOT_FOUND)
        return True

    @staticmethod
    async def limit_type_is_not_supported(
            obj: t.Union[None, UUID, BaseModel, list[BaseModel]],
    ) -> bool:
        """Raise exception if limit type is not supported."""
        if not obj:
            raise NotFoundError(name=LIMIT_TYPE_IS_NOT_SUPPORTED)
        return True
