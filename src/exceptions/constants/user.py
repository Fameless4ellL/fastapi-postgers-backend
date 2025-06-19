""" User exceptions """
from src.exceptions.schemas import ErrorMessage


USER_NOT_FOUND = ErrorMessage(
    message="User not found",
    code_error="UserNotFound"
)
USER_IS_BLOCKED = ErrorMessage(
    message="User is blocked",
    code_error="UserIsBlocked"
)
