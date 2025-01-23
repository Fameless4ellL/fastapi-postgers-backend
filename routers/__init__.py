from contextlib import asynccontextmanager
from aiogram import Bot, Dispatcher
from fastapi import APIRouter
from settings import settings

from models.db import DBSessionMiddleware


@asynccontextmanager
async def lifespan_tg(*args, **kwargs):
    try:
        if not settings.debug:
            await bot.set_webhook(settings.bot_webhook)
        yield
    finally:
        await bot.session.close()


bot = Bot(token=settings.bot_token)
dp = Dispatcher(bot=bot)
dp.update.outer_middleware(DBSessionMiddleware())

public = APIRouter(prefix="/v1", tags=["v1"], lifespan=lifespan_tg)
admin = APIRouter(prefix="/v1/admin", tags=["admin"])


from .app import *  # noqa
from .tg import *  # noqa
from .admin import *  # noqa
from .auth import *  # noqa
