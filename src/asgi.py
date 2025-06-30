import logging
from typing import AsyncIterator, Union

from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from httpx import AsyncClient

from src.middlewares import RequestMiddleware
from src.models import Action
from src.routers import public, admin_, cron_
from settings import settings
from src.schemes import BadResponse
from src.exceptions.schemas import ErrorMessage
from src.handler import add_exception_handlers


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("LOGS")

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
if settings.debug:
    console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
log.addHandler(console_handler)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, AsyncClient]]:
    async with AsyncClient() as client:
        yield {"client": client}


def init_routers(app_: FastAPI) -> None:
    app_.include_router(public)
    app_.include_router(admin_)
    app_.include_router(cron_)


def create_app() -> FastAPI:
    app_ = FastAPI(
        title="Bingo API Gateway",
        description="""
        Bingo is a secure, modular, and scalable API designed to power next-generation applications.

        - **Version**: 0.9.9
        - **Environment-Aware**: Documentation visibility adapts to `settings.debug`.
        - **Error Handling**: Common 400 responses unified under structured models (`ErrorMessage`, `BadResponse`).

        This API gateway centralizes access for public and internal consumers, streamlining authentication,
        validation, and routing across service boundaries.
        """,
        version="0.9.9",
        responses={
            400: {"model": Union[ErrorMessage, BadResponse]},
            422: {"model": ErrorMessage},
        },
        lifespan=lifespan,
        swagger_ui_parameters={
            "docExpansion": "list",
            "persistAuthorization": True,
            "displayRequestDuration": True,
            "filter": True,
            "layout": "BaseLayout",
            "deepLinking": True,
        },
        # docs_url=None if settings.debug else "/docs",
        # redoc_url=None if settings.debug else "/redoc",
    )
    init_routers(app_)

    def custom_openapi():
        if app_.openapi_schema:
            return app_.openapi_schema

        openapi_schema = get_openapi(
            title=app_.title,
            version=app_.version,
            description=app_.description,
            routes=app_.routes,
        )

        actions = {i.value for i in Action}

        for path in openapi_schema.get("paths", {}).values():
            for operation in path.values():
                if "tags" in operation:
                    operation["tags"] = [
                        tag for tag in operation["tags"] if tag not in actions
                    ]

        app_.openapi_schema = openapi_schema
        return app_.openapi_schema

    app_.openapi = custom_openapi

    origins = ['*']
    app_.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    app_.add_middleware(RequestMiddleware)
    add_exception_handlers(app_)
    return app_


fastapp = create_app()
