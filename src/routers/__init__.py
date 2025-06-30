from contextlib import asynccontextmanager
from aiogram import Bot, Dispatcher
from fastapi import APIRouter, Depends, HTTPException
from settings import settings
from src.models.db import DBSessionMiddleware
from src.utils.dependencies import Permission
from .admin import (
    network,
    currencies,
    admins,
    dashboard,
    finance,
    games_router,
    admin_panel_auth,
    bingo,
    jackpots,
    profile,
    kyc,
    users,
    referral
)
from .app import public_games
from .auth import public_auth
from .user import users_router
from .instabingo import public_instabingo
from .utils import settings_router


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


def init_admin_routers(app_: APIRouter) -> None:
    app_.include_router(network)
    app_.include_router(currencies)
    app_.include_router(admins)
    app_.include_router(dashboard)
    app_.include_router(finance)
    app_.include_router(games_router)
    app_.include_router(bingo)
    app_.include_router(jackpots)
    app_.include_router(profile)
    app_.include_router(kyc)
    app_.include_router(users)
    app_.include_router(referral)

def init_public_routers(app_: APIRouter) -> None:
    app_.include_router(admin_panel_auth)
    app_.include_router(public_games)
    app_.include_router(public_auth)
    app_.include_router(users_router)
    app_.include_router(public_instabingo)
    app_.include_router(settings_router)


public = APIRouter(prefix="/v1",  lifespan=lifespan)
admin_ = APIRouter(prefix="/v1/admin", dependencies=[Depends(Permission())])
cron_ = APIRouter(
    prefix="/v1/cron",
    tags=["cron"],
    dependencies=[Depends(cron_key)],
    include_in_schema=settings.debug
)

init_admin_routers(admin_)
init_public_routers(public)


from .tg import *  # noqa
from .admin import *  # noqa
from .cron import *  # noqa
from .jackpot import * # noqa