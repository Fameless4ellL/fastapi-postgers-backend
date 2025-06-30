"""Game exceptions."""

import typing as t
from uuid import UUID
from pydantic import BaseModel
from src.exceptions.base import NotFoundError, ValuePydanticError
from src.exceptions.constants.game import (
    GAME_NOT_FOUND,
    ERR_MIN_NUMBERS_CONDITION, ERR_NUMBER_CONDITION
)
from src.models import GameType


class GameExceptions:
    """Game exceptions class."""
    @staticmethod
    async def raise_exception_game_not_found(
        game: t.Union[None, UUID, BaseModel, list[BaseModel]],
    ) -> bool:
        """Raise exception if game not found."""
        if not game:
            raise NotFoundError(name=GAME_NOT_FOUND)
        return True

    @staticmethod
    async def raise_exception_on_local_game(
        game: t.Union[object, None],
        user: t.Union[object, None],
    ) -> bool:
        """
        Raise exception if local game not found.

        Args:
            game: Game(Base) Table
            user: User(Base) Table

        """
        if (
            game.game_type == GameType.LOCAL
            and str(game.country) != user.country
        ):
            raise NotFoundError(name=GAME_NOT_FOUND)

    @staticmethod
    async def raise_exception_on_game_conditions(
        game: t.Union[object, None],
        numbers: list[set[int]]
    ) -> bool:
        """
        Raise exception if local game not found.

        Args:
            game: Game(Base) Table
            numbers (list[set[int]]): list of list numbers for game to buy a ticket

        """
        if any(len(n) != game.limit_by_ticket for n in numbers):
            raise ValuePydanticError(ERR_MIN_NUMBERS_CONDITION)

        for number in numbers:
            if not all(0 < i <= game.max_limit_grid for i in number):
                raise ValuePydanticError(ERR_NUMBER_CONDITION)

