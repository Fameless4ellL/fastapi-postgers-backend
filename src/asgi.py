import logging
from typing import AsyncIterator, Union

from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from httpx import AsyncClient

from src.middlewares import RequestMiddleware
from src.routers import public, admin, _cron
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


fastapp = FastAPI(lifespan=lifespan, responses={400: {"model": Union[ErrorMessage, BadResponse]}})

fastapp.include_router(public)
fastapp.include_router(admin)
fastapp.include_router(_cron)
fastapp.mount("/static", app=StaticFiles(directory="static"), name="static")

origins = ['*']

fastapp.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
fastapp.add_middleware(RequestMiddleware)
add_exception_handlers(fastapp)
