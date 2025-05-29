from typing import Annotated

from fastapi import Depends, Path, status, Security
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.models.db import get_db, get_sync_db
from src.models.other import InstaBingo, Ticket, Currency, Number
from src.models.user import Role, User
from src.routers import admin
from src.routers.admin import get_crud_router
from src.utils.dependencies import get_admin_token
from src.schemes.admin import (
    InstaBingoFilter,
    InstaBingoSchema,
    InstaBingos,
    InstaBingoCreate,
    InstaBingoUpdate,
    InstaBingoList,
    Empty,
    Countries
)
from src.schemes import BadResponse

get_crud_router(
    model=InstaBingo,
    prefix="/bingo",
    schema=InstaBingos,
    get_schema=InstaBingoSchema,
    create_schema=InstaBingoCreate,
    update_schema=InstaBingoUpdate,
    files=Annotated[Empty, Depends(Empty)],
    filters=Annotated[Countries, Depends(Countries)],
    security_scopes=[
        Role.SUPER_ADMIN.value,
        Role.ADMIN.value,
        Role.GLOBAL_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ]
)


@admin.get(
    "/instabingo/default",
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.ADMIN.value,
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.FINANCIER.value,
            Role.SUPPORT.value
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def get_instabingo_defafult(
    db: Annotated[Session, Depends(get_sync_db)],
):
    """
    get instabingo default
    """
    default = db.query(
        InstaBingo
    ).filter(
        InstaBingo.country.is_(None)
    ).first()

    if not default:
        currency = db.query(Currency).first()
        if not currency:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=BadResponse(message="Currency not found").model_dump()
            )

        game = InstaBingo(
            currency_id=currency.id,
            country=None
        )
        db.add(game)
        db.commit()

        default = db.query(InstaBingo).filter(
            InstaBingo.country.is_(None),
        ).first()

    data = {
        "id": default.id,
        "country": default.country,
        "price": float(default.price),
        "currency_id": default.currency_id,
        "created_at": default.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data
    )


@admin.get(
    "/instabingos",
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.ADMIN.value,
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.FINANCIER.value,
            Role.SUPPORT.value
        ])],
    responses={
        400: {"model": BadResponse},
        200: {"model": InstaBingoList}
    },
)
async def get_instabingo_tickets_list(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Annotated[InstaBingoFilter, Depends(InstaBingoFilter)],
    offset: int = 0,
    limit: int = 10,
):
    """
    Get all instabingo games
    """
    stmt = select(
        Ticket.id,
        Ticket.user_id,
        Ticket.won,
        User.username,
        User.country,
        Ticket.created_at,
        Ticket.amount,
    ).join(
        User, Ticket.user_id == User.id
    ).join(
        InstaBingo, Ticket.instabingo_id == InstaBingo.id
    ).filter(
        InstaBingo.id == Ticket.instabingo_id
    )

    if item.countries:
        stmt = stmt.filter(User.country.in_(item.countries))

    if item.date_from:
        stmt = stmt.filter(Ticket.created_at >= item.date_from)

    if item.date_to:
        stmt = stmt.filter(Ticket.created_at <= item.date_to)

    if item.filter:
        stmt = stmt.filter(
            or_(
                Ticket.id.ilike(f"%{item.filter}%"),
                User.username.ilike(f"%{item.filter}%"),
                User.id.ilike(f"%{item.filter}%"),
            )
        )

    game = await db.execute(stmt.offset(offset).limit(limit))
    game = game.fetchall()

    count_stmt = stmt.with_only_columns(func.count())
    count_result = await db.execute(count_stmt)
    count = count_result.scalar()

    data = [{
        "ticket_id": i.id,
        "user_id": i.user_id,
        "username": i.username,
        "country": i.country,
        "created_at": i.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "won": i.won,
        "amount": float(i.amount)
    } for i in game]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=InstaBingoList(**{"count": count, "data": data}).model_dump()
    )


@admin.get(
    "/instabingo/{game_id}",
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.ADMIN.value,
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.FINANCIER.value,
            Role.SUPPORT.value
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def get_instabingo_ticket(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
):
    """
    Get instabingo game
    """
    stmt = select(
        Ticket.id,
        Ticket.instabingo_id,
        Ticket.user_id,
        Ticket.won,
        User.username,
        User.country,
        Currency.code,
        Ticket.created_at,
        Ticket.amount,
        Ticket.numbers,
    ).join(
        User, Ticket.user_id == User.id
    ).join(
        InstaBingo, Ticket.instabingo_id == InstaBingo.id
    ).join(
        Currency, InstaBingo.currency_id == Currency.id
    ).filter(
        Ticket.id == game_id
    )

    game = await db.execute(stmt)
    game = game.fetchone()

    if not game:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content="Game not found"
        )

    data = {
        "id": game.id,
        "user_id": game.user_id,
        "username": game.username,
        "country": game.country,
        "numbers": game.numbers,
        "currency": game.code,
        "created_at": game.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "won": game.won,
        "amount": float(game.amount)
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data
    )


@admin.get(
    "/instabingo/{game_id}/gnumbers",
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.ADMIN.value,
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.FINANCIER.value,
            Role.SUPPORT.value
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def get_generated_numbers(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
):
    """
    Get generated numbers
    """
    stmt = select(Number).filter(Number.ticket_id == game_id)
    numbers = await db.execute(stmt)
    numbers = numbers.scalars().all()

    data = [{
        "id": i.id,
        "number": i.number,
        "start_date": i.start_date.strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": i.end_date.strftime("%Y-%m-%d %H:%M:%S"),
    } for i in numbers]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data
    )


@admin.delete(
    "/bingo/{instabingo_id}",
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.ADMIN.value,
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.FINANCIER.value,
            Role.SUPPORT.value
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def set_instabingo_as_deleted(
    db: Annotated[AsyncSession, Depends(get_db)],
    instabingo_id: Annotated[int, Path()],
):
    """
    set instabingo as deleted
    """
    stmt = select(InstaBingo).filter(InstaBingo.id == instabingo_id)
    number = await db.execute(stmt)
    number = number.scalar_one_or_none()

    if not number:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Instabingo not found"
        )

    number.deleted = True
    db.add(number)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content="Instabingo deleted"
    )
