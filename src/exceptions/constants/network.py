""" Network constants """
from src.exceptions.schemas import ErrorMessage


NETWORK_NOT_FOUND = ErrorMessage(
    message="Network not found",
    code_error="NetworkNotFound"
)
NETWORK_IS_NOT_CONNECTED = ErrorMessage(
    message="Network is not connected",
    code_error="NetworkIsNotConnected"
)
