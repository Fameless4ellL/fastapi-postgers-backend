"""Pydantic errors validation."""

from src.exceptions.constants.pydantic import UNEXPECTED_ERROR
from src.exceptions.schemas import ErrorMessage

VALIDATION_ERROR_MESSAGES = {}

BAD_REQUEST_CODE = "unexpectedError"


async def get_validation_error_message(pydantic_error: dict) -> str:
    """Create an error message."""
    return VALIDATION_ERROR_MESSAGES.get(f"{pydantic_error['loc'][1]}", pydantic_error["msg"])


async def generate_validation_error_code(pydantic_error: dict) -> str:
    """Create an error code."""
    if not isinstance(pydantic_error["loc"][1], str):
        return BAD_REQUEST_CODE
    return f"wrong_{pydantic_error['loc'][1].capitalize()}"


async def generate_validation_error_response(pydantic_error: dict) -> ErrorMessage:
    """Function to generate error response."""
    if len(pydantic_error["loc"]) <= 1:
        return UNEXPECTED_ERROR
    return ErrorMessage(
        message=await get_validation_error_message(pydantic_error),
        code_error=await generate_validation_error_code(pydantic_error),
    )
