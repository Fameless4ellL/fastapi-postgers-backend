from contextlib import asynccontextmanager
from aiogram import Bot, Dispatcher
from fastapi import APIRouter, HTTPException, Depends
from settings import settings
from models.db import DBSessionMiddleware


@asynccontextmanager
async def lifespan(*args, **kwargs):
    try:
        if not settings.debug:
            await bot.set_webhook(settings.bot_webhook)
        yield
    finally:
        await bot.session.close()


def cron_key(key: str = ""):
    if key != settings.cron_key:
        raise HTTPException(status_code=404, detail="Not found")
    return True


bot = Bot(token=settings.bot_token)
dp = Dispatcher(bot=bot)
dp.update.outer_middleware(DBSessionMiddleware())

public = APIRouter(prefix="/v1", tags=["v1"], lifespan=lifespan)
admin = APIRouter(prefix="/v1/admin", tags=["admin"])


from .app import *  # noqa
from .tg import *  # noqa
from .admin import *  # noqa
from .auth import *  # noqa
from .user import *  # noqa
