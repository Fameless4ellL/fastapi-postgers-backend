import logging
from typing import AsyncIterator, Union

from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from httpx import AsyncClient

from src.middlewares import RequestMiddleware
from src.routers import public, admin, _cron, network
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
    app_.include_router(admin)
    app_.include_router(_cron)
    app_.include_router(network)


def create_app() -> FastAPI:
    app_ = FastAPI(
        title="Bingo API Gateway",
        description="""
        Bingo is a secure, modular, and scalable API designed to power next-generation applications.

        - **Version**: 1.0.0
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
    init_routers(app_=app_)

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
