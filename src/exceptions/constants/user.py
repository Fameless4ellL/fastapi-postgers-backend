""" User exceptions """
from src.exceptions.schemas import ErrorMessage


USER_NOT_FOUND = ErrorMessage(
    message="User not found",
    code_error="UserNotFound"
)
