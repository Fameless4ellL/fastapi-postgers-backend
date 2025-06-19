""" Limit constants """
from src.exceptions.schemas import ErrorMessage


LIMIT_NOT_FOUND = ErrorMessage(
    message="Limit not found",
    code_error="LimitNotFound"
)
LIMIT_TYPE_IS_NOT_SUPPORTED = ErrorMessage(
    message="Unsupported limit type",
    code_error="UnsupportedType"
)
