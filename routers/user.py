import os
from eth_account import Account
import pycountry
import json
from decimal import Decimal
from typing import Annotated, List
from fastapi import Depends, status, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from eth_account.signers.local import LocalAccount
from sqlalchemy.orm import joinedload
from tronpy.keys import to_base58check_address
from models.db import get_db
from models.user import Balance, User, Wallet, BalanceChangeHistory
from models.other import Currency, Ticket
from routers import public
from globals import aredis
from routers.utils import get_user, get_currency

from sqlalchemy.ext.asyncio import AsyncSession
from schemes.base import BadResponse, Country
from schemes.game import (
    Tickets, Withdraw
)
from schemes.user import Profile, UserBalance
from utils.workers import add_to_queue


@public.get(
    "/profile",
    tags=["user"],
    responses={400: {"model": BadResponse}, 200: {"model": Profile}}
)
async def profile(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Получение информации о пользователе
    """
    
    # sum balances
    balances = await db.execute(
        select(func.sum(Balance.balance))
        .filter(Balance.user_id == user.id)
    )
    balance = float(balances.scalar() or 0)

    wallet_result = await db.execute(
        select(Wallet)
        .filter(Wallet.user_id == user.id)
    )
    wallet = wallet_result.scalar()
    if not wallet:
        acc: LocalAccount = Account.create()

        wallet = Wallet(
            user_id=user.id,
            address=acc.address,
            private_key=acc.key.hex()
        )
        db.add(wallet)
        await db.commit()

        await aredis.sadd("BLOCKER:WALLETS", wallet.address)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Profile(
            balance=balance,
            locale=user.language_code or "EN",
            address={
                "base58": to_base58check_address(wallet.address),
                "evm": wallet.address,
            },
            country=user.country,
            username=user.username
        ).model_dump()
    )


@public.get(
    "/balance",
    tags=["user"],
    responses={400: {"model": BadResponse}, 200: {"model": List[UserBalance]}}
)
async def balance(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Получение balance пользователя
    """

    balancies = await db.execute(
        select(Balance).options(
            joinedload(Balance.currency).joinedload(Currency.network)
        )
        .filter(Balance.user_id == user.id)
    )
    balance = balancies.scalars().all()

    if not balance:
        currencies = await db.execute(select(Currency))
        for currency in currencies.scalars().all():
            bal = Balance(
                user_id=user.id,
                currency_id=currency.id,
            )
            db.add(bal)
        await db.commit()

        balancies = await db.execute(
            select(Balance).options(
                joinedload(Balance.currency).joinedload(Currency.network)
            )
            .filter(Balance.user_id == user.id)
        )
        balance = balancies.scalars().all()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=[UserBalance(
            network=b.currency.network.symbol,
            currency=b.currency.code,
            balance=float(b.balance)
        ).model_dump() for b in balance]
    )


@public.post("/withdraw", tags=["user"])
async def withdraw(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    currency: Annotated[Currency, Depends(get_currency)],
    item: Withdraw
):
    """
    Вывод средств
    """
    wallet_result = await db.execute(
        select(Wallet)
        .filter(Wallet.user_id == user.id)
    )
    wallet = wallet_result.scalar()

    if not wallet:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Wallet not found"
        )

    balance_result = await db.execute(
        select(Balance)
        .with_for_update()
        .filter(
            Balance.user_id == user.id,
            Balance.currency_id == currency.id
        )
    )
    balance = balance_result.scalar()
    if not balance:
        balance = Balance(user_id=user.id)
        db.add(balance)

    if balance.balance < item.amount:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Insufficient funds"
        )

    history = BalanceChangeHistory(
        user_id=user.id,
        balance_id=balance.id,
        currency_id=currency.id,
        change_amount=item.amount,
        change_type="withdraw",
        status=BalanceChangeHistory.Status.PENDING,
        previous_balance=balance.balance - Decimal(item.amount),
        new_balance=balance.balance,
        args=json.dumps({"address": item.address})
    )

    db.add(history)

    balance.balance -= Decimal(item.amount)
    db.add(balance)

    await db.commit()

    add_to_queue(
        "withdraw",
        history_id=history.id,
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@public.post("/upload", tags=["user"])
async def upload_document(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile
):
    """
    Загрузка документа
    """
    if not file.content_type.startswith("image"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Invalid file type"
        )

    directory = "static/kyc"
    os.makedirs(directory, exist_ok=True)

    # Delete old file if it exists
    if user.document:
        old_file_path = os.path.join(directory, user.document)
        if os.path.exists(old_file_path):
            os.remove(old_file_path)

    # Save file to disk
    file_path = os.path.join(directory, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    user.document = file.filename
    db.add(user)
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
        "game_instance_id": t.game_id,
        "currency": t.currency.code if t.currency else None,
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
        "name": country.name,
        "flag": country.flag
    } for country in pycountry.countries]

    # по запросу фронта, ага
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data
    )


@public.get(
    "/history", tags=["user"],
    responses={400: {"model": BadResponse}, 200: {"model": Tickets}}
)
async def get_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_user)],
    skip: int = 0,
    limit: int = 10,
):
    """
    Получение истории изменения баланса
    """
    history = await db.execute(
        select(BalanceChangeHistory)
        .filter(BalanceChangeHistory.user_id == user.id)
        .order_by(BalanceChangeHistory.created_at.desc())
        .offset(skip).limit(limit)
    )
    history = history.scalars().all()

    data = [{
        "id": h.id,
        "amount": float(h.change_amount),
        "type": h.change_type,
        "status": str(h.status),
        "created": h.created_at.timestamp()
    } for h in history]

    count_result = await db.execute(
        select(func.count(BalanceChangeHistory.id))
        .filter(BalanceChangeHistory.user_id == user.id)
    )
    count = count_result.scalar()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=dict(tickets=data, count=count)
    )
