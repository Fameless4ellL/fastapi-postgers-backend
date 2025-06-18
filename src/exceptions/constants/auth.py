""" Authorization exceptions """
from src.exceptions.schemas import ErrorMessage


PERMISSION_DENIED = ErrorMessage(
    message="You do not have permission to perform this",
    code_error="PermissionDenied"
)
NO_SCOPE = ErrorMessage(
    message="Token does not have any scope permissions",
    code_error="InvalidToken"
)
TOKEN_NOT_FOUND = ErrorMessage(
    message="Token not found",
    code_error="InvalidToken"
)
BAD_TOKEN = ErrorMessage(
    message="Bad Token",
    code_error="InvalidToken"
)
INVALID_AUTH = ErrorMessage(
    message="Invalid authorization code",
    code_error="InvalidToken"
)
INVALID_SCHEME = ErrorMessage(
    message="Invalid authentication scheme",
    code_error="InvalidToken"
)
