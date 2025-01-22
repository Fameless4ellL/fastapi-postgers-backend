from pydantic import BaseModel, Field


class BadResponse(BaseModel):
    message: str = Field(default="Bad Request")