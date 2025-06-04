"""Api exception."""
from http import HTTPStatus
from typing import Union

from fastapi import HTTPException


class ApiException(HTTPException):
    """Api exception class."""
    def __init__(
            self: object,
            name: Union[str, dict],
            status_code: Union[HTTPStatus, int] = HTTPStatus.BAD_REQUEST,
    ) -> None:
        """Initialize api exception class."""
        self.name = name
        self.status_code = status_code or HTTPStatus.BAD_REQUEST
