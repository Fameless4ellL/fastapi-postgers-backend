"""Exception handlers."""

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from src.exceptions.api import ApiException
from src.exceptions.base import (
    BadRequestError, ConflictError,
    ForbiddenError, NotFoundError,
    UnauthorizedError,
    ValuePydanticError
)


def add_exception_handlers(app: FastAPI) -> None:
    """App exception handlers."""

    # TODO let front prepare
    # @app.exception_handler(RequestValidationError)
    # async def custom_form_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    #     pydantic_error = exc.errors()[0]
    #     return JSONResponse(
    #         status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    #         content=jsonable_encoder(
    #             await generate_validation_error_response(pydantic_error=pydantic_error),
    #         ),
    #     )

    @app.exception_handler(ApiException)
    async def unicorn_exception_handler(request: Request, exc: ApiException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(exc.name),
        )

    @app.exception_handler(NotFoundError)
    async def not_found_exception_handler(
            request: Request,
            exc: NotFoundError,
            status_code: status = status.HTTP_404_NOT_FOUND) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(exc.name),
        )

    @app.exception_handler(ConflictError)
    async def conflict_exception_handler(
            request: Request,
            exc: ConflictError,
            status_code: status = status.HTTP_409_CONFLICT) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(exc.name),
        )

    @app.exception_handler(UnauthorizedError)
    async def unauthorized_exception_handler(
            request: Request,
            exc: UnauthorizedError,
            status_code: status = status.HTTP_401_UNAUTHORIZED) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(exc.name),
        )

    @app.exception_handler(ValuePydanticError)
    async def value_error_exception_handler(
            request: Request,
            exc: ValuePydanticError,
            status_code: status = status.HTTP_422_UNPROCESSABLE_ENTITY) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(exc.name),
        )

    @app.exception_handler(ForbiddenError)
    async def forbidden_error_exception_handler(
            request: Request,
            exc: ForbiddenError,
            status_code: status = status.HTTP_403_FORBIDDEN) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(exc.name),
        )

    @app.exception_handler(BadRequestError)
    async def bad_request_error_exception_handler(
            request: Request,
            exc: BadRequestError,
            status_code: status = status.HTTP_400_BAD_REQUEST) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(exc.name),
        )
