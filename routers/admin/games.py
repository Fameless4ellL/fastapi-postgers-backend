import os
from fastapi import Depends, Path, UploadFile, status, Security
from fastapi.responses import JSONResponse
from apscheduler.jobstores.base import JobLookupError
from typing import Annotated, Literal

from sqlalchemy import select, func, orm, exists
from models.log import Action
from models.user import Role, User
from models.other import Currency, Game, GameStatus, GameView, Ticket
from routers import admin
from routers.admin import get_crud_router
from routers.utils import get_admin_token
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import get_db, get_sync_db
from schemes.admin import (
    GameFilter,
    GameUpload,
    GameSchema,
    Games,
    GameCreate,
    GameUpdate,
)
from globals import scheduler
from schemes.base import BadResponse, JsonForm


get_crud_router(
    model=Game,
    prefix="/games",
    schema=Games,
    get_schema=GameSchema,
    create_schema=Annotated[GameCreate, JsonForm()],
    update_schema=Annotated[GameUpdate, JsonForm()],
    files=Annotated[GameUpload, Depends(GameUpload)],
    filters=Annotated[GameFilter, Depends(GameFilter)],
    security_scopes=[
        Role.SUPER_ADMIN.value,
        Role.ADMIN.value,
        Role.GLOBAL_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ]
)


@admin.delete(
    "/games/{game_id}",
    tags=[Action.ADMIN_DELETE],
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.ADMIN.value,
            Role.SUPER_ADMIN.value
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def delete_game(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
    _type: Literal["delete", "cancel"],
):
    stmt = select(Game).filter(Game.id == game_id)
    game = await db.execute(stmt)
    game = game.scalar()
    if not game:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content="Game not found"
        )

    tickets = select(exists().where(Ticket.game_id == game_id))
    tickets = await db.execute(tickets)
    tickets = tickets.scalar()
    if tickets:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Game has tickets"
        )

    if _type == "delete":
        game.status = GameStatus.DELETED

    if _type == "cancel":
        game.repeat = False
        game.status = GameStatus.CANCELLED

    try:
        scheduler.remove_job(f"game_{game.id}")
    except JobLookupError:
        pass

    db.add(game)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK, content="Success"
    )


@admin.get(
    "/games/{game_id}/purchased",
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.ADMIN.value,
            Role.SUPER_ADMIN.value
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def get_purchased_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
):
    """
    ticket purchased total by one Game separately from currency
    """

    stmt = select(
        Currency.code,
        func.sum(Ticket.amount).label("amount"),
        func.count(Ticket.id).label("pcs"),
        Game.prize,
    ).join(
        Game, Ticket.game_id == Game.id
    ).join(
        Currency, Game.currency_id == Currency.id
    ).filter(
        Ticket.game_id == game_id,
    ).group_by(
        Currency.code,
        Game.prize
    )
    tickets = await db.execute(stmt)
    tickets = tickets.fetchall()
    tickets = next(iter(tickets), None)

    if not tickets:
        data = {
            'pcs': 0,
            'currency': "USDT",
            'amount': 0,
            'prize': 0,
        }
    else:
        data = {
            'pcs': tickets.pcs,
            'currency': tickets.code,
            'amount': float(tickets.amount),
            'prize': float(tickets.prize),
        }

    return JSONResponse(
        status_code=status.HTTP_200_OK, content=data
    )


@admin.get(
    "/games/{game_id}/participants",
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.ADMIN.value,
            Role.SUPER_ADMIN.value
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def get_participants(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10,
):
    """
    participants total by one Game
    """
    stmt = select(
        Ticket.id,
        Ticket.user_id,
        func.count(Ticket.id).label("tickets"),
        func.sum(Ticket.amount).label("amount"),
        Ticket.created_at,
        User.username
    ).distinct(
        Ticket.user_id
    ).join(
        User, Ticket.user_id == User.id
    ).filter(
        Ticket.game_id == game_id
    ).group_by(
        Ticket.id,
        Ticket.user_id,
        Ticket.created_at,
        User.username
    )
    tickets = await db.execute(stmt.offset(offset).limit(limit))
    tickets = tickets.fetchall()

    data = [{
        "id": ticket.id,
        "user_id": ticket.user_id,
        "user": ticket.username,
        "tickets": ticket.tickets,
        "amount": float(ticket.amount),
        "date": ticket.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for ticket in tickets]

    return JSONResponse(
        status_code=status.HTTP_200_OK, content=data
    )


@admin.get(
    "/games/{game_id}/participants/{user_id}",
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.ADMIN.value,
            Role.SUPER_ADMIN.value
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def get_participant_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
    user_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10,
):
    """
    get tickets by user_id from game_id
    """
    stmt = select(
        Ticket.id,
        Ticket.user_id,
        Ticket.numbers,
        Ticket.created_at,
        User.username
    ).join(
        User, Ticket.user_id == User.id
    ).filter(
        Ticket.game_id == game_id,
        Ticket.user_id == user_id
    )
    tickets = await db.execute(stmt.offset(offset).limit(limit))
    tickets = tickets.fetchall()

    data = [{
        "id": ticket.id,
        "user_id": ticket.user_id,
        "user": ticket.username,
        "tickets": ticket.numbers,
        "date": ticket.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for ticket in tickets]

    return JSONResponse(
        status_code=status.HTTP_200_OK, content=data
    )


@admin.get(
    "/games/{game_id}/winners",
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.ADMIN.value,
            Role.SUPER_ADMIN.value
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def get_winners(
    db: Annotated[orm.Session, Depends(get_sync_db)],
    game_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10,
):
    """
    get winners by  game_id
    """
    tickets = db.query(
        Ticket.id,
        Ticket.user_id,
        func.sum(Ticket.amount).label("amount"),
        Ticket.created_at,
        User.username
    ).join(
        User, Ticket.user_id == User.id
    ).filter(
        Ticket.game_id == game_id,
        Ticket.won.is_(True)
    ).group_by(
        Ticket.id,
        Ticket.user_id,
        Ticket.created_at,
        User.username
    ).offset(offset).limit(limit)
    tickets = tickets.all()

    data = [{
        "id": ticket.id,
        "user_id": ticket.user_id,
        "user": ticket.user.username,
        "status": "paid" if ticket.amount > 0 else "not paid",
        "amount": float(ticket.amount),
        "date": ticket.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for ticket in tickets]

    return JSONResponse(
        status_code=status.HTTP_200_OK, content=data
    )


@admin.put(
    "/games/{game_id}/winners/{ticket_id}",
    tags=[Action.ADMIN_UPDATE],
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.ADMIN.value,
            Role.SUPER_ADMIN.value
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def set_ticket_status(
    db: Annotated[orm.Session, Depends(get_sync_db)],
    game_id: Annotated[int, Path()],
    ticket_id: Annotated[int, Path()],
):
    """
    set ticket prize has been paid for material game
    """
    ticket = db.query(Ticket).filter(
        Ticket.id == ticket_id,
        Ticket.game_id == game_id,
    ).join(
        Game, Ticket.game_id == Game.id
    ).filter(
        Game.kind == GameView.MATERIAL
    ).first()

    if not ticket:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content="Ticket not found"
        )

    # TODO set ticket prize has been paid


    return JSONResponse(
        status_code=status.HTTP_200_OK, content="Unimplemented"
    )
