""" Jackpot constants """
from src.exceptions.schemas import ErrorMessage


JACKPOT_NOT_FOUND = ErrorMessage(
    message="Jackpot not found",
    code_error="JackpotNotFound"
)
JACKPOT_ALREADY_STARTED = ErrorMessage(
    message="Jackpot has already started",
    code_error="JackpotAlreadyStarted"
)