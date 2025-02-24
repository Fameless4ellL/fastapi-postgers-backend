import pycountry
import json
from decimal import Decimal
from typing import Annotated
from fastapi import Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from web3 import AsyncWeb3
from models.db import get_db
from models.user import Balance, User, Wallet, BalanceChangeHistory
from models.other import Currency, Ticket
from routers import public
from routers.utils import get_user, get_currency, get_w3
from utils.signature import get_password_hash
from eth_account.signers.local import LocalAccount
from sqlalchemy.ext.asyncio import AsyncSession
from schemes.base import BadResponse, Country
from globals import aredis
from web3.types import TxReceipt
from schemes.game import (
    Tickets, Deposit, Withdraw
)
from schemes.user import Profile
from utils.workers import add_to_queue


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

    total_balance = float(balance.balance)
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
    w3: Annotated[AsyncWeb3, Depends(get_w3)],
    item: Deposit
):
    """
    Пополнение баланса
    """
    # check if balance history exists with this hash
    balance_change_history = await db.execute(
        select(BalanceChangeHistory)
        .filter(BalanceChangeHistory.proof == item.hash)
    )
    balance_change_history = balance_change_history.scalar()

    if balance_change_history:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Transaction already processed"
        )

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

    tx: TxReceipt = w3.eth.wait_for_transaction_receipt(item.hash, timeout=60)

    currency = await db.execute(
        select(Currency)
        .filter(Currency.code == "USDC")
    )
    currency = currency.scalar()
    if not currency:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Currency not found"
        )

    contract = w3.eth.contract(
        address=tx.contractAddress,
        abi=json.loads(await aredis.get("abi"))
    )

    logs = contract.events.Transfer().process_receipt(tx)

    transfer = {}
    for log in logs:
        if log.event != "Transfer":
            continue

        transfer = log.args
        break

    decimals = 18

    if tx is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Transaction not found"
        )

    if (
        tx.status != 1
        or transfer.to.lower() != wallet.address.lower()
    ):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Transaction failed"
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

    amount = Decimal(transfer.value / 10 ** decimals)

    if not balance:
        balance = Balance(
            user_id=user.id,
            currency_id=currency.id,
            balance=amount
        )
        db.add(balance)
    else:
        balance.balance += amount

    history = BalanceChangeHistory(
        user_id=user.id,
        balance_id=balance.id,
        currency_id=currency.id,
        change_amount=amount,
        change_type="deposit",
        previous_balance=balance.balance - amount,
        proof=item.hash,
        new_balance=balance.balance
    )

    db.add(history)
    await db.commit()

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


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
        .filter(Balance.user_id == user.id)
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
        change_type="withdrawal",
        status=BalanceChangeHistory.Status.PENDING,
        previous_balance=balance.balance - Decimal(item.amount),
        new_balance=balance.balance
    )

    db.add(history)

    balance.balance -= Decimal(item.amount)
    db.add(balance)

    await db.commit()

    add_to_queue(
        "withdraw",
        {"history_id": history.id, }
    )

    return JSONResponse(status_code=status.HTTP_200_OK)


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
