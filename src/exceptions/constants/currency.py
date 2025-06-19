""" Currency constants """
from src.exceptions.schemas import ErrorMessage


CURRENCY_NOT_FOUND = ErrorMessage(
    message="Currency not found",
    code_error="CurrencyNotFound"
)