import pycountry
from typing import Annotated
from fastapi import Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from web3 import AsyncWeb3
from models.db import get_db
from models.user import Balance, User, Wallet
from models.other import Ticket
from routers import public
from routers.utils import get_user, get_currency, get_w3
from utils.signature import get_password_hash
from eth_account.signers.local import LocalAccount
from sqlalchemy.ext.asyncio import AsyncSession
from schemes.base import BadResponse, Country
from schemes.game import (
    Tickets, Deposit, Withdraw
)
from schemes.user import Profile


@public.get(
    "/profile",
    tags=["user"],
    responses={400: {"model": BadResponse}, 200: {"model": Profile}}
)
async def balance(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    currency: Annotated[str, Depends(get_currency)],
    w3: Annotated[AsyncWeb3, Depends(get_w3)]
):
    """
    Получение информации о пользователе
    """
    balance_result = await db.execute(
        select(Balance)
        .filter(
            Balance.user_id == user.id,
            Balance.currency_id == currency.id
        )
    )
    balance = balance_result.scalar()
    if not balance:
        balance = Balance(
            user_id=user.id,
            currency_id=currency.id,
        )
        db.add(balance)
        await db.commit()

    wallet_result = await db.execute(
        select(Wallet)
        .filter(Wallet.user_id == user.id)
    )
    wallet = wallet_result.scalar()
    if not wallet:

        acc: LocalAccount = w3.eth.account.create()

        hash_password = get_password_hash(acc.key.hex())

        wallet = Wallet(
            user_id=user.id,
            address=acc.address,
            private_key=hash_password
        )
        db.add(wallet)
        await db.commit()

    total_balance = balance.balance
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Profile(
            balance=total_balance,
            locale=user.language_code or "EN",
            address=wallet.address,
            country=user.country,
            username=user.username
        ).model_dump()
    )


@public.post("/deposit", tags=["user"])
async def deposit(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Deposit
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
        balance.balance += item.amount
        await db.commit()

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@public.post("/withdraw", tags=["user"])
async def withdraw(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Withdraw
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
        balance.balance -= item.amount
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


@public.get(
    "/countries", tags=["settings"],
    responses={400: {"model": BadResponse}, 200: {"model": Country}}
)
async def get_countries():
    """
    Получение список стран
    """
    data = [{
        "alpha_3": country.alpha_3,
        "name": country.name
    } for country in pycountry.countries]

    # по запросу фронта, ага
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data
    )
