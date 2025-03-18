from fastapi import Depends, Path, Query, status, Security
from fastapi.responses import JSONResponse
from typing import Annotated, Optional
from pydantic_extra_types.country import CountryAlpha3

from sqlalchemy import func, select, or_
from models.user import Balance, User, Role, Wallet, BalanceChangeHistory
from models.other import Game, Ticket, Jackpot
from routers import admin
from sqlalchemy.orm import joinedload
from routers.utils import Token, get_admin_token
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import get_db
from schemes.admin import (
    BalanceBase,
    HistoryList,
    UserJackpots,
    UserTickets,
    Users,
    UserInfo as UserScheme,
    UserGames,
    WalletBase,
)
from schemes.base import BadResponse


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
    country: Annotated[Optional[CountryAlpha3], Query(...)] = None,
    offset: int = 0,
    limit: int = 10,
):
    """
    Get all users
    """
    stmt = select(User).filter(User.role == "user")

    if country:
        stmt = stmt.filter(User.country == country)

    if Role.LOCAL_ADMIN in token.scopes:
        stmt = stmt.filter(User.country == token.country)

    if query:
        stmt = stmt.filter(
            or_(
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

    data = {
        "id": user.id,
        "username": user.username,
        "telegram_id": user.telegram_id,
        "language_code": user.language_code,
        "phone_number": user.phone_number,
        "country": user.country,
        "email": user.email,
        "role": user.role,
        "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": user.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        "tickets": {"purchased": tickets or 0},
        "winnings": {"winnings": winnings or 0},
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
            "amount": float(game_instance.won_amount),
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

    count = await db.execute(
        stmt.with_only_columns(func.count(Jackpot.id))
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
        }
        for game_instance in game_instances
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=UserJackpots(games=data, count=count).model_dump(),
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
    Get user's balance history
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
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.FINANCIER.value,
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
    Get user's balance history
    """
    stmt = select(Wallet).filter(Wallet.user_id == user_id)

    result = await db.execute(stmt)
    wallet = result.scalar()

    if not wallet:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Wallet not found"},
        )

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
    stmt = select(Balance).options(
        joinedload(Balance.currency)
    ).filter(Balance.user_id == user_id)

    result = await db.execute(stmt)
    balance = result.scalars().all()

    data = [
        {
            "id": b.id,
            "balance": float(b.balance),
            "currency": b.currency.code if b.currency else None,
        } for b in balance
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data,
    )
