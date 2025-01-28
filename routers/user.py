from typing import Annotated
from fastapi import Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from models.db import get_db
from models.user import Balance, User
from models.other import Ticket
from routers import public
from routers.utils import get_user
from sqlalchemy.ext.asyncio import AsyncSession
from schemes.base import BadResponse
from schemes.game import (
    Tickets,
)


@public.get("/profile", tags=["user"])
async def balance(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Получение информации о пользователе
    """
    balance_result = await db.execute(
        select(Balance)
        .filter(Balance.user_id == user.id)
    )
    balance = balance_result.scalar()
    if not balance:
        balance = Balance(user_id=user.id)
        db.add(balance)
        await db.commit()

    total_balance = balance.balance
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "balance": total_balance,
            "locale": user.language_code or "EN"
        }
    )


@public.post("/deposit", tags=["user"])
async def deposit(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    amount: float
):
    # TODO TEMP
    balance_result = await db.execute(
        select(Balance)
        .with_for_update()
        .filter(Balance.user_id == user.id)
    )
    balance = balance_result.scalar()
    if not balance:
        balance = Balance(user_id=user.id)
        db.add(balance)
        await db.commit()
    else:
        balance.balance += amount
        await db.commit()

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@public.post("/withdraw", tags=["user"])
async def withdraw(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    amount: float
):
    # TODO TEMP
    balance_result = await db.execute(
        select(Balance)
        .with_for_update()
        .filter(Balance.user_id == user.id)
    )
    balance = balance_result.scalar()
    if not balance:
        balance = Balance(user_id=user.id)
        db.add(balance)
        await db.commit()
    else:
        balance.balance -= amount
        await db.commit()

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@public.get(
    "/tickets", tags=["user"],
    responses={400: {"model": BadResponse}, 200: {"model": Tickets}}
)
async def get_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_user)],
    skip: int = 0,
    limit: int = 10,
):
    """
    Получение билетов пользователя
    """
    tickets = await db.execute(
        select(Ticket)
        .filter(Ticket.user_id == user.id)
        .offset(skip).limit(limit)
    )
    tickets = tickets.scalars().all()

    data = [{
        "id": t.id,
        "game_instance_id": t.game_instance_id,
        "numbers": t.numbers,
        "demo": t.demo,
        "won": t.won,
        "amount": float(t.amount),
        "created": t.created_at.timestamp()
    } for t in tickets]

    count_result = await db.execute(
        select(func.count(Ticket.id))
        .filter(Ticket.user_id == user.id)
    )
    count = count_result.scalar()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Tickets(tickets=data, count=count).model_dump()
    )
