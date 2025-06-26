""" Game constants """
from src.exceptions.schemas import ErrorMessage


GAME_NOT_FOUND = ErrorMessage(
    message="Game not found",
    code_error="GameNotFound"
)
ERR_MIN_NUMBERS_CONDITION = ErrorMessage(
    message="Invalid condition numbers for game",
    code_error="InvalidCondition"
)
ERR_NUMBER_CONDITION = ErrorMessage(
    message="Invalid ticket numbers, need proper number based on game settings",
    code_error="InvalidCondition"
)
