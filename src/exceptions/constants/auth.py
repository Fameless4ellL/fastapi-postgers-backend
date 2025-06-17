""" Authorization exceptions """
from src.exceptions.schemas import ErrorMessage


PERMISSION_DENIED = ErrorMessage(
    message="You do not have permission to perform this",
    code_error="PermissionDenied"
)