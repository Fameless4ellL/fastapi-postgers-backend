from typing import Annotated
from fastapi import Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from models.db import get_db
from models.user import User
from models.other import (
    Currency,
    InstaBingo,
)
from routers import public
from routers.utils import generate_game, get_user, nth, url_for
from sqlalchemy.ext.asyncio import AsyncSession
from schemes.base import BadResponse
from globals import aredis
from schemes.instabingo import InstaBingoInfo
from settings import settings
from utils.web3 import transfer


@public.get(
    "/instabingo", tags=["InstaBingo"],
    responses={404: {"model": BadResponse}, 200: {"model": InstaBingoInfo}},
)
async def get_instabingo(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Получение нужной информации для игры в инстабинго
    """
    stmt = select(
        InstaBingo.id,
        InstaBingo.price,
        InstaBingo.prize,
        Currency.code
    ).join(
        Currency, InstaBingo.currency_id == Currency.id
    ).where(
        InstaBingo.country == user.country
    )
    data = await db.execute(stmt)
    data = data.scalar()

    if not data:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=InstaBingoInfo().model_dump()
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=InstaBingoInfo(data).model_dump()
    )
