from contextlib import asynccontextmanager
from aiogram import Bot, Dispatcher
from fastapi import APIRouter, Depends
from settings import settings
from src.models.db import DBSessionMiddleware
from src.utils.dependencies import Permission


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

public = APIRouter(prefix="/v1",  lifespan=lifespan)
admin = APIRouter(prefix="/v1/admin", dependencies=[Depends(Permission())])
_cron = APIRouter(
    prefix="/v1/cron",
    tags=["cron"],
    dependencies=[Depends(cron_key)],
    include_in_schema=settings.debug
)


from .app import *  # noqa
from .tg import *  # noqa
from .admin import *  # noqa
from .auth import *  # noqa
from .user import *  # noqa
from .cron import *  # noqa
from .instabingo import *  # noqa