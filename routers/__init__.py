from contextlib import asynccontextmanager
from aiogram import Bot, Dispatcher
from fastapi import APIRouter
from settings import settings

from models.db import DBSessionMiddleware


@asynccontextmanager
async def lifespan_tg(*args, **kwargs):
    try:
        yield
    finally:
        await bot.session.close()


bot = Bot(token=settings.bot_token)
dp = Dispatcher(bot=bot)
dp.update.outer_middleware(DBSessionMiddleware())

router = APIRouter(prefix="/v1", tags=["v1"], lifespan=lifespan_tg)


from .app import *  # noqa
from .tg import *
