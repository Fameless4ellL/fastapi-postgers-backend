from typing import Annotated, Optional

from eth_account import Account
from eth_account.signers.local import LocalAccount
from fastapi import Depends, Path, Query, status, Security
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.globals import aredis
from src.models.db import get_db
from src.models.other import Currency, Game, GameView, Network, Ticket, Jackpot, InstaBingo
from src.models.user import Balance, User, Role, Wallet, BalanceChangeHistory, Document
from src.routers import admin
from src.schemes import BadResponse, Country_by_name
from src.schemes.admin import (
    BalanceBase,
    HistoryList,
    UserJackpots,
    UserTickets,
    Users,
    UserInfo as UserScheme,
    UserGames,
    WalletBase,
)
from src.utils.dependencies import Token, get_admin_token
from src.utils.validators import url_for


@admin.get(
    "/users",
    responses={
        400: {"model": BadResponse},
        200: {"model": Users},
    },
)
async def get_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[Token, Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ]),],
    query: Annotated[Optional[str], Query(...)] = None,
    countries: Optional[list[Country_by_name]] = Query(None),
    offset: int = 0,
    limit: int = 10,
):
    """
    Get all users
    """
    stmt = select(User).filter(User.role == "user")
    if countries:
        # list of countries
        stmt = stmt.filter(User.country.in_(countries))

    if Role.LOCAL_ADMIN in token.scopes:
        stmt = stmt.filter(User.country == token.country)

    if query:
        stmt = stmt.filter(
            or_(
                User.id.ilike(f"%{query}%"),
                User.username.ilike(f"%{query}%"),
                User.phone_number.ilike(f"%{query}%"),
            )
        )

    users = await db.execute(stmt.offset(offset).limit(limit))
    users = users.scalars().all()

    count = await db.execute(stmt.with_only_columns(func.count(User.id)))
    count = count.scalar()

    data = [
        {
            "id": user.id,
            "username": user.username,
            "phone_number": user.phone_number,
            "country": user.country,
        }
        for user in users
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Users(users=data, count=count).model_dump(),
    )


@admin.get(
    "/users/{user_id}",
    responses={
        400: {"model": BadResponse},
        200: {"model": UserScheme},
    },
)
async def get_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[Token, Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ]),],
    user_id: Annotated[int, Path()],
):
    """
    Get all users
    """
    stmt = select(User).filter(User.id == user_id, User.role == "user")

    if Role.LOCAL_ADMIN in token.scopes:
        stmt = stmt.filter(User.country == token.country)

    user = await db.execute(stmt)
    user = user.scalars().first()

    if not user:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "User not found"},
        )

    stmt = select(func.count(Ticket.id)).filter(User.id == user_id)
    tickets = await db.execute(stmt)
    tickets = tickets.scalar()
    winnings = await db.execute(
        select(func.sum(Ticket.amount)).filter(
            Ticket.id == user_id, Ticket.won.is_(True)
        )
    )
    winnings = winnings.scalar()

    material_winnings = select(
        Game.prize
    ).join(
        Ticket, Ticket.game_id == Game.id
    ).filter(
        Ticket.user_id == user_id,
        Ticket.won.is_(True)
    ).offset(0).limit(3)
    material_winnings = await db.execute(material_winnings)
    material_winnings = material_winnings.scalars().all()

    docs = await db.execute(
        select(Document)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
        .limit(4)
    )
    documents = docs.scalars().all()
    documents = [
        url_for("static/kyc", path=doc.file.name)
        for doc in documents
    ]

    data = {
        "id": user.id,
        "firstname": user.firstname,
        "lastname": user.lastname,
        "username": user.username,
        "patronymic": user.patronomic,
        "telegram": user.telegram,
        "telegram_id": user.telegram_id,
        "language_code": user.language_code,
        "phone_number": user.phone_number,
        "country": user.country,
        "email": user.email,
        "role": user.role,
        "kyc_status": user.kyc,
        "document": documents,
        "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": user.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        "tickets": {"purchased": tickets or 0},
        "winnings": {
            "cash": winnings or 0,
            "material": list(material_winnings)
        },
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK, content=UserScheme(**data).model_dump()
    )


@admin.get(
    "/users/{user_id}/games",
    responses={
        400: {"model": BadResponse},
        200: {"model": UserGames},
    },
)
async def get_user_games(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[Token, Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ]),],
    user_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10,
):
    """
    Get all user's games
    """
    stmt = select(User).filter(User.id == user_id, User.role == "user")

    if Role.LOCAL_ADMIN in token.scopes:
        stmt = stmt.filter(User.country == token.country)

    user = await db.execute(stmt)
    user = user.scalars().first()

    if not user:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "User not found"},
        )

    stmt = (
        select(
            Game.id,
            Game.name,
            Game.scheduled_datetime,
            func.count(Ticket.id).label("tickets_purchased"),
            func.sum(func.coalesce(Ticket.amount, 0))
            .filter(Ticket.won.is_(True))
            .label("won_amount"),
        )
        .join(Ticket, Ticket.game_id == Game.id)
        .filter(Ticket.user_id == user_id)
        .group_by(Game.id, Game.name)
    )

    result = await db.execute(stmt.offset(offset).limit(limit))
    game_instances = result.fetchall()

    count = await db.execute(
        stmt.with_only_columns(func.count(Game.id))
    )
    count = count.scalar() or 0

    data = [
        {
            "game_instance_id": game_instance.id,
            "game_name": game_instance.name,
            "scheduled_datetime": (
                game_instance.scheduled_datetime.strftime("%Y-%m-%d %H:%M:%S")
                if game_instance.scheduled_datetime
                else None
            ),
            "tickets_purchased": game_instance.tickets_purchased,
            "amount": float(game_instance.won_amount) if game_instance.won_amount else 0,
        }
        for game_instance in game_instances
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=UserGames(games=data, count=count).model_dump(),
    )


@admin.get(
    "/users/{user_id}/games/{game_id}",
    dependencies=[Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value])],
    responses={
        400: {"model": BadResponse},
        200: {"model": UserTickets},
    },
)
async def get_user_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Path()],
    game_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10,
):
    """
    Get user's tickets for a specific game
    """
    stmt = (
        select(
            Ticket.id,
            Game.name.label("game_name"),
            Ticket.number,
            Ticket.numbers,
            Ticket.created_at.label("date_and_time"),
            Ticket.won,
            Ticket.amount
        )
        .join(Game, Game.id == Ticket.game_id)
        .filter(
            Ticket.user_id == user_id,
            Game.id == game_id,
        )
    )

    result = await db.execute(stmt.offset(offset).limit(limit))
    tickets = result.fetchall()

    count = await db.execute(stmt.with_only_columns(func.count(Ticket.id)))
    count = count.scalar() or 0

    data = [
        {
            "id": ticket.id,
            "game_name": ticket.game_name,
            "number": ticket.number,
            "numbers": ticket.numbers,
            "date_and_time": (
                ticket.date_and_time.strftime("%Y-%m-%d %H:%M:%S")
                if ticket.date_and_time
                else None
            ),
            "won": ticket.won,
            "amount": float(ticket.amount),
        }
        for ticket in tickets
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"tickets": data, "count": len(data)},
    )


@admin.get(
    "/users/{user_id}/jackpots",
    dependencies=[Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value])],
    responses={
        400: {"model": BadResponse},
        200: {"model": UserJackpots},
    },
)
async def get_user_jackpots(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10,
):
    """
    Get user's jackpots for a specific game
    """
    stmt = (
        select(
            Jackpot.id,
            Jackpot.name,
            Jackpot.scheduled_datetime,
            func.count(Ticket.id).label("tickets_purchased"),
        )
        .join(Ticket, Ticket.jackpot_id == Jackpot.id)
        .filter(Ticket.user_id == user_id)
        .group_by(Jackpot.id, Jackpot.name)
    )

    result = await db.execute(stmt.offset(offset).limit(limit))
    game_instances = result.fetchall()

    count_stmt = (
        select(func.count(Jackpot.id.distinct()))
        .join(Ticket, Ticket.jackpot_id == Jackpot.id)
        .filter(Ticket.user_id == user_id)
    )
    count_result = await db.execute(count_stmt)
    count = count_result.scalar() or 0

    data = [
        {
            "jackpot_instance_id": game_instance.id,
            "game_name": game_instance.name,
            "scheduled_datetime": (
                game_instance.scheduled_datetime.strftime("%Y-%m-%d %H:%M:%S")
                if game_instance.scheduled_datetime
                else None
            ),
            "tickets_purchased": game_instance.tickets_purchased,
        }
        for game_instance in game_instances
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=UserJackpots(jackpots=data, count=count).model_dump(),
    )


@admin.get(
    "/users/{user_id}/jackpots/{game_id}",
    dependencies=[Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value])],
    responses={
        400: {"model": BadResponse},
        200: {"model": UserTickets},
    },
)
async def get_user_tickets_by_jackpots(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Path()],
    game_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10,
):
    """
    Get user's tickets for a specific jackpot
    """
    stmt = (
        select(
            Ticket.id,
            Jackpot.name.label("game_name"),
            Ticket.number,
            Ticket.numbers,
            Ticket.created_at.label("date_and_time"),
            Ticket.won,
            Ticket.amount
        )
        .join(Jackpot, Jackpot.id == Ticket.jackpot_id)
        .filter(
            Ticket.user_id == user_id,
            Jackpot.id == game_id,
        )
    )

    result = await db.execute(stmt.offset(offset).limit(limit))
    tickets = result.fetchall()

    count = await db.execute(stmt.with_only_columns(func.count(Ticket.id)))
    count = count.scalar() or 0

    data = [
        {
            "id": ticket.id,
            "game_name": ticket.game_name,
            "number": ticket.number,
            "numbers": ticket.numbers,
            "date_and_time": (
                ticket.date_and_time.strftime("%Y-%m-%d %H:%M:%S")
                if ticket.date_and_time
                else None
            ),
            "won": ticket.won,
            "amount": float(ticket.amount),
        }
        for ticket in tickets
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"tickets": data, "count": len(data)},
    )


@admin.get(
    "/users/{user_id}/transactions",
    dependencies=[Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ])],
    responses={
        400: {"model": BadResponse},
        200: {"model": HistoryList},
    },
)
async def get_user_transactions(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10,
):
    """
    Get user's transactions
    """
    stmt = select(BalanceChangeHistory).filter(BalanceChangeHistory.user_id == user_id)

    result = await db.execute(stmt.order_by(
    ).offset(offset).limit(limit))
    history = result.scalars().all()

    count = await db.execute(stmt.with_only_columns(func.count(BalanceChangeHistory.id)))
    count = count.scalar() or 0

    data = [
        {
            "id": h.id,
            "change_type": h.change_type,
            "amount": h.change_amount,
            "date_and_time": h.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "status": h.status,
        }
        for h in history
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=HistoryList(items=data, count=count).model_dump(mode='json'),
    )


@admin.get(
    "/users/{user_id}/wallet",
    dependencies=[Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ])],
    responses={
        400: {"model": BadResponse},
        200: {"model": WalletBase},
    },
)
async def get_user_wallet(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Path()],
):
    """
    Get user wallet
    """
    stmt = select(Wallet).filter(Wallet.user_id == user_id)

    result = await db.execute(stmt)
    wallet = result.scalar()

    if not wallet:
        acc: LocalAccount = Account.create()

        wallet = Wallet(
            user_id=user_id,
            address=acc.address,
            private_key=acc.key.hex()
        )
        db.add(wallet)
        await db.commit()

        await aredis.sadd("BLOCKER:WALLETS", wallet.address)

    data = {
        "id": wallet.id,
        "address": wallet.address,
        "date_and_time": wallet.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data,
    )


@admin.get(
    "/users/{user_id}/balance",
    dependencies=[Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ])],
    responses={
        400: {"model": BadResponse},
        200: {"model": BalanceBase},
    },
)
async def get_user_balance(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Path()],
):
    """
    Get user's balance
    """
    stmt = (
        select(
            Currency.id,
            Currency.code,
            Network.symbol,
            func.coalesce(func.sum(Balance.balance), 0).label("balance")
        )
        .outerjoin(Balance, and_(Balance.currency_id == Currency.id, Balance.user_id == user_id))
        .outerjoin(Network, Currency.network_id == Network.id)
        .group_by(Currency.id, Currency.code, Network.symbol)
    )

    result = await db.execute(stmt)
    balances = result.fetchall()

    data, total = [], 0
    for b in balances:
        data.append({
            "id": b.id,
            "balance": float(b.balance),
            "network": b.symbol,
            "currency": b.code
        })

        total += float(b.balance)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"balances": data, "total": total},
    )


@admin.get(
    "/users/{user_id}/winings",
    dependencies=[Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def get_user_winings(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10,
):
    """
    Get user's winings Tickets
    """
    # get ticket with join jackpot, game, instabingo
    stmt = (
        select(
            Ticket.id,
            Currency.code,
            Ticket.instabingo_id,
            Ticket.jackpot_id,
            Ticket.game_id,
            Ticket.number,
            Ticket.numbers,
            Ticket.amount,
            Ticket.won
        )
        .join(Currency, Currency.id == Ticket.currency_id)
        .filter(
            Ticket.user_id == user_id,
            Ticket.won.is_(True)
        )
    )

    result = await db.execute(stmt.offset(offset).limit(limit))
    tickets = result.fetchall()

    count = await db.execute(stmt.with_only_columns(func.count(Ticket.id)))
    count = count.scalar() or 0

    data = []
    for ticket in tickets:
        if ticket.instabingo_id:
            instabingo = await db.execute(
                select(InstaBingo).filter(
                    InstaBingo.id == ticket.instabingo_id
                )
            )
            instabingo = instabingo.scalar()

            game_id = instabingo.id
            game_name = "InstaBingo"

            amount = f"{ticket.amount} {ticket.code}"

        elif ticket.jackpot_id:
            jackpot = await db.execute(
                select(Jackpot).filter(Jackpot.id == ticket.jackpot_id)
            )
            jackpot = jackpot.scalar()

            game_id = jackpot.id
            game_name = "Jackpot"

            amount = f"{jackpot.amount} {ticket.code}"

        elif ticket.game_id:
            game = await db.execute(
                select(Game).filter(Game.id == ticket.game_id)
            )
            game = game.scalar()

            game_id = game.id
            game_name = "Game"

            if game.kind == GameView.MONETARY:
                amount = f"{ticket.amount} {ticket.code}"
            else:
                amount = game.prize

        else:
            continue

        data.append({
            "id": ticket.id,
            "number": ticket.number,
            "numbers": ticket.numbers,
            "game_id": game_id,
            "type": game_name,
            "amount": str(amount),
        })
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"tickets": data, "count": count},
    )
