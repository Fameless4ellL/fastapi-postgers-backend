"""Network exceptions."""

import typing as t
from uuid import UUID
from pydantic import BaseModel
from web3 import Web3

from src.exceptions.base import NotFoundError, UnavailableServiceError
from src.exceptions.constants.network import (
    NETWORK_NOT_FOUND, NETWORK_IS_NOT_CONNECTED,
)


class NetworkExceptions:
    """User exceptions class."""
    @staticmethod
    async def network_not_found(
        obj: t.Union[None, UUID, BaseModel, list[BaseModel]],
    ) -> bool:
        """Raise exception if user not found."""
        if not obj:
            raise NotFoundError(name=NETWORK_NOT_FOUND)
        return True

    @staticmethod
    async def network_is_not_connected(obj: Web3) -> bool:
        """Raise exception if user not found."""
        if not obj.is_connected():
            raise UnavailableServiceError(name=NETWORK_IS_NOT_CONNECTED)
        return True
