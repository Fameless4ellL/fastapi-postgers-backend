"""Base app error."""

from typing import Union

from src.exceptions.schemas import ErrorMessage


class BaseAppError(Exception):
    """Base app error class."""
    def __init__(
        self: object,
        name: Union[ErrorMessage, str],
    ) -> None:
        """Initialize a new base app error class."""
        self.name = name


class NotFoundError(BaseAppError):
    """Not found error class."""


class ConflictError(BaseAppError):
    """Conflict error class."""


class UnauthorizedError(BaseAppError):
    """Unauthorized error class."""


class ForbiddenError(BaseAppError):
    """Forbidden error class."""


class ValuePydanticError(BaseAppError):
    """Value pydantic error class."""


class BadRequestError(BaseAppError):
    """Bad request error class."""


class UnavailableServiceError(BaseAppError):
    """Unavailable service error class."""


class TooManyRequestsError(BaseAppError):
    """Too many requests error class."""
