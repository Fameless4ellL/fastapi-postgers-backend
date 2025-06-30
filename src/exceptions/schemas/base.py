"""An error message schema."""

from pydantic import BaseModel, Field, ConfigDict


class ErrorMessage(BaseModel):
    """
    Standard schema for API error responses.

    - `message`: Descriptive text explaining the error.
    - `code_error`: Identifier for the error type, used for programmatic handling.

    Examples:
    - 403 Forbidden: `{"message": "You do not have permission to perform this", "code_error": "PermissionDenied"}`
    - 404 Not Found: `{"message": "Limit not found", "code_error": "LimitNotFound"}`
    - 422 Validation: `{"message": "{field description}", "code_error": "wrong_{field}"}`

    This schema helps clients understand why a request failed and what type of error occurred.
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "message": "You do not have permission to perform this",
                    "code_error": "PermissionDenied",
                },
                {
                    "message": "{field description}",
                    "code_error": "wrong_{field}"
                },
                {
                    "message": "Limit not found",
                    "code_error": "LimitNotFound"
                }
            ],
        }
    )

    message: str = Field(
        ...,
        description="this is desc",
        examples=[
            "You do not have permission to perform this",
            "Token does not have any scope permissions",
            "Token not found",
            "Bad Token",
            "{model} not found",
        ]
    )
    code_error: str = Field(
        ...,
        description="this is desc",
        examples=[
            "PermissionDenied",
            "InvalidToken",
            "InvalidPassword",
            "IdenticalPassword",
            "GameNotFound",
            "{model}NotFound"
        ]
    )
