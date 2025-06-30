from typing import Annotated
from fastapi import Depends
from sqlalchemy import func, select

from src.models.db import get_db
from src.models.user import User
from src.models.other import (
    GameStatus,
    Jackpot,
    Ticket,
    JackpotType,
)
from src.routers import public
from src.utils.dependencies import get_user
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemes import (
    Jackpot as JackpotModel,
)


@public.get(
    "/jackpots",
    tags=["v1.public.jackpots"],
    responses={200: {"model": JackpotModel}}
)
async def get_jackpots(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Получение списка джекпотов
    """
    stmt = select(
        func.sum(Ticket.amount).label("total_tickets"),
        Jackpot.id,
        Jackpot.status,
        Jackpot.image,
        Jackpot.scheduled_datetime,
        Jackpot.percentage,
        Jackpot.created_at,
    ).outerjoin(Ticket, Ticket.jackpot_id == Jackpot.id).filter(
        Jackpot.status == GameStatus.PENDING,
        Jackpot._type == JackpotType.LOCAL,
        Jackpot.country == user.country
    ).group_by(Jackpot.id).offset(0).limit(5)
    local = await db.execute(stmt)
    local = local.fetchall() or []

    stmt = select(
        func.sum(Ticket.amount).label("total_tickets"),
        Jackpot.id,
        Jackpot.status,
        Jackpot.image,
        Jackpot.scheduled_datetime,
        Jackpot.percentage,
        Jackpot.created_at,
    ).outerjoin(Ticket, Ticket.jackpot_id == Jackpot.id).filter(
        Jackpot.status == GameStatus.PENDING,
        Jackpot._type == JackpotType.GLOBAL,
    ).group_by(Jackpot.id).offset(0).limit(5)
    global_ = await db.execute(stmt)
    global_ = global_.fetchall() or []

    data = [
        {
            "id": j.id,
            "status": j.status.value,
            "endtime": j.scheduled_datetime.timestamp(),
            "image": j.image,
            "amount": float(j.total_tickets or 0),
            "percentage": float(j.percentage),
            "created": j.created_at.timestamp()
        } for j in local + global_
    ]

    return data