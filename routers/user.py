import importlib
import json
from decimal import Decimal
from typing import Annotated, List

import pycountry
from eth_account import Account
from eth_account.signers.local import LocalAccount
from fastapi import Depends, Query, status, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from tronpy.keys import to_base58check_address

from globals import aredis, q
from models.db import get_db
from models.log import Action
from models.other import Currency, GameStatus, Ticket
from models.user import (
    Balance,
    Kyc,
    Notification,
    User,
    Wallet,
    BalanceChangeHistory, Document
)
from routers import public
from routers.utils import get_user, get_currency, url_for, get_user_token, worker
from schemes.base import BadResponse, Country, JsonForm
from schemes.game import (
    MyGames, MyGamesType, Tickets, Withdraw
)
from schemes.user import KYC, Notifications, Profile, UserBalance, Usersettings, Transactions


@public.get(
    "/profile",
    tags=["user"],
    responses={
        400: {"model": BadResponse},
        200: {"model": Profile}
    }
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

    data = None
    document = await db.execute(
        select(Document)
        .filter(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
    )
    document = document.scalar()

    if document:
        data = {
            "first_name": user.firstname,
            "patronomic": user.patronomic,
            "last_name": user.lastname,
            "document": url_for("static/kyc", path=document.file.name),
        }

    notifications = await db.execute(
        select(exists().where(
            Notification.user_id == user.id,
            Notification.read.is_(False)
        ))
    )
    notifications = notifications.scalar()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Profile(
            balance=balance,
            kyc=data,
            locale=user.language_code or "EN",
            address={
                "base58": to_base58check_address(wallet.address),
                "evm": wallet.address,
            },
            notifications=notifications,
            country=user.country or "USA",
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


@public.post("/withdraw", tags=["user", Action.WITHDRAW])
async def withdraw(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    currency: Annotated[Currency, Depends(get_currency)],
    item: Withdraw
):
    """
    Вывод средств
    """
    # check kyc status
    stmt = select(Kyc).filter(Kyc.country == user.country)
    kyc = await db.execute(stmt)
    kyc = kyc.scalar()
    if kyc and not user.kyc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="KYC required"
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

    q.enqueue_at(
        item.datetime,
        getattr(worker, "withdraw"),
        history.id,
        job_id=f"withdraw_{history.id}",
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@public.post(
    "/upload",
    tags=["user", Action.UPDATE],
    responses={400: {"model": BadResponse}, 200: {"model": str}}
)
async def upload_kyc(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Annotated[KYC, JsonForm()],
    files: List[UploadFile],
    avatar: Annotated[UploadFile, File(include_in_schema=False)] = None
):
    """
    Загрузка документа
    """
    user.firstname = item.first_name
    user.lastname = item.last_name
    user.patronomic = item.patronomic

    if avatar:
        avatar.filename = f"{user.id}_{avatar.filename}"
        user.avatar_v1 = avatar

    db.add(user)

    for file in files:
        if not file.content_type.startswith("image"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content="Invalid file type"
            )

        file.filename = f"{user.id}_{file.filename}"
        doc = Document(
            user_id=user.id,
            file=file
        )
        db.add(doc)

    await db.commit()

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@public.get(
    "/tickets", tags=["user"],
    responses={400: {"model": BadResponse}, 200: {"model": Tickets}}
)
async def get_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_user)],
    game_id: int = None,
    jackpot_id: int = None,
    skip: int = 0,
    limit: int = 10,
):
    """
    Получение билетов пользователя
    """
    stmt = select(Ticket).filter(Ticket.user_id == user.id)

    if game_id:
        stmt = stmt.filter(Ticket.game_id == game_id)

    if jackpot_id:
        stmt = stmt.filter(Ticket.jackpot_id == jackpot_id)

    tickets = await db.execute(stmt.offset(skip).limit(limit))
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
async def get_countries(
    q: str = Query('', description="Search query")
):
    """
    Получение список стран
    """
    try:
        if q:
            countries = pycountry.countries.search_fuzzy(q)
        else:
            countries = pycountry.countries
    except LookupError:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=[]
        )

    data = [{
        "alpha_3": country.alpha_3,
        "name": country.name,
        "flag": country.flag
    } for country in countries]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data
    )


@public.get(
    "/history", tags=["user"],
    responses={
        400: {"model": BadResponse},
        200: {"model": Transactions}
    }
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
        select(
            BalanceChangeHistory.id,
            BalanceChangeHistory.change_amount,
            BalanceChangeHistory.change_type,
            BalanceChangeHistory.status,
            Currency.code.label("currency"),
            BalanceChangeHistory.created_at,
        )
        .join(Currency, BalanceChangeHistory.currency_id == Currency.id)
        .filter(BalanceChangeHistory.user_id == user.id)
        .order_by(BalanceChangeHistory.created_at.desc())
        .offset(skip).limit(limit)
    )
    history = history.fetchall()

    data = [{
        "id": h.id,
        "amount": h.change_amount,
        "currency": h.currency,
        "type": h.change_type,
        "status": h.status,
        "created": h.created_at.timestamp()
    } for h in history]

    count_result = await db.execute(
        select(func.count(BalanceChangeHistory.id))
        .filter(BalanceChangeHistory.user_id == user.id)
    )
    count = count_result.scalar()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Transactions(
            items=data,
            count=count
        ).model_dump(mode='json')
    )


@public.get(
    "/mygames", tags=["user"],
    responses={400: {"model": BadResponse}, 200: {"model": MyGames}}
)
async def get_my_games(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_user)],
    item: MyGamesType,
    skip: int = 0,
    limit: int = 10,
):
    """
    Получение игр пользователя в котором он участвовал
    """
    # TODO refactor
    model = importlib.import_module("models.other")
    model = getattr(model, item.model)

    # list of games or jackpots by user distinct
    stmt = select(model).join(Ticket).options(
        joinedload(model.currency)
    ).filter(
        Ticket.user_id == user.id
    )

    items = await db.execute(stmt.offset(skip).limit(limit))
    items = items.scalars().fetchall()

    data = []
    for i in items:
        # Calculate the sum of Ticket.amount for the chosen game
        sum_stmt = select(
            Ticket.won,
            func.sum(Ticket.amount).label("total_amount")
        ).filter(
            Ticket.user_id == user.id,
            Ticket.won.is_(True),
        ).group_by(
            Ticket.won
        )
        if item.model == "Game":
            sum_stmt = sum_stmt.filter(Ticket.game_id == i.id)

        elif item.model == "Jackpot":
            sum_stmt = sum_stmt.filter(Ticket.jackpot_id == i.id)

        elif item.model == "InstaBingo":
            sum_stmt = sum_stmt.filter(Ticket.instabingo_id == i.id)

        sum_result = await db.execute(sum_stmt)
        ticket = sum_result.first()
        if not ticket:
            ticket = {
                "won": False,
                "total_amount": 0
            }
        else:
            ticket = {
                "won": ticket.won,
                "total_amount": float(ticket.total_amount)
            }
        if item.model == "InstaBingo":
            data.append({
                "id": i.id,
                "currency": i.currency.code if i.currency else None,
                "status": GameStatus.COMPLETED.value,
                "name": "InstaBingo",
                "price": i.price,
                "created": i.created_at.timestamp(),
                "endtime": i.created_at.timestamp()
            } | ticket)
        elif item.model == "Jackpot":
            amount = getattr(i, "amount", '0') or '0'
            data.append({
                "id": i.id,
                "currency": i.currency.code if i.currency else None,
                "name": i.name,
                "image": url_for("static", path=i.image),
                "status": i.status.value if i.status else "None",
                "price": getattr(i, "price", 0),
                "max_limit_grid": getattr(i, "max_limit_grid", 0),
                "prize": float(amount) if str(amount).isnumeric() else amount,
                "endtime": i.scheduled_datetime.timestamp(),
                "created": i.created_at.timestamp(),
            } | ticket)
        else:
            data.append({
                "id": i.id,
                "currency": i.currency.code if i.currency else None,
                "name": i.name,
                "image": url_for("static", path=i.image),
                "status": i.status.value if i.status else "None",
                "price": getattr(i, "price", 0),
                "max_limit_grid": getattr(i, "max_limit_grid", 0),
                "prize": float(i.prize) if i.prize.isnumeric() else i.prize,
                "endtime": i.scheduled_datetime.timestamp(),
                "created": i.created_at.timestamp(),
            } | ticket)

    stmt = select(func.count(model.id)).join(Ticket).filter(
        Ticket.user_id == user.id
    )
    count_result = await db.execute(stmt)
    count = count_result.scalar()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=MyGames(games=data, count=count).model_dump()
    )


@public.get(
    "/notifications", tags=["user"],
    responses={400: {"model": BadResponse}, 200: {"model": Notifications}}
)
async def get_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_user_token)],
    skip: int = 0,
    limit: int = 10,
):
    """
    Получение уведомлений для пользователя
    """

    stmt = select(Notification).filter(Notification.user_id == user.id)
    notifications = await db.execute(stmt.offset(skip).limit(limit))
    notifications = notifications.scalars().all()

    data = [{
        "id": n.id,
        "head": n.head,
        "body": n.body,
        "args": json.loads(n.args),
        "created": n.created_at.timestamp()
    } for n in notifications]

    count_stmt = select(func.count(Notification.id)).filter(
        Notification.user_id == user.id
    )
    count_result = await db.execute(count_stmt)
    count = count_result.scalar()

    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id)
        .values(read=True)
    )
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=dict(items=data, count=count)
    )


@public.post(
    "/settings", tags=["user", Action.UPDATE],
    responses={400: {"model": BadResponse}, 200: {"model": Notifications}}
)
async def set_settings(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_user)],
    item: Usersettings,
):
    """
    Изменение настроек пользователя
    """

    user.language_code = item.locale
    user.country = item.country
    db.add(user)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content="OK"
    )
