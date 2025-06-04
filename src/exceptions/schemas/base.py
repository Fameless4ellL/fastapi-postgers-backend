"""An error message schema."""

from pydantic import BaseModel


class ErrorMessage(BaseModel):
    """An error message schema."""
    message: str
    code_error: str
