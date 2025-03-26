from fastapi import Depends, Path, Security, status
from fastapi.responses import JSONResponse
from typing import Annotated, Literal, Optional, Union
from apscheduler.jobstores.base import JobLookupError
from models.log import Action

from sqlalchemy import func, select, or_
from models.user import User, Role
from models.other import Game, GameStatus, Jackpot, Ticket, RepeatType
from routers import admin
from routers.admin import get_crud_router
from routers.utils import get_admin_token, send_mail, url_for
from globals import scheduler, aredis
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import get_db
from schemes.admin import (
    GameUpload,
    JackpotBase,
    Jackpots,
    JackpotCreate,
    JackpotUpdate,
    Empty,
    JackpotFilter,
)
from schemes.base import BadResponse, JsonForm


get_crud_router(
    model=Jackpot,
    prefix="/jackpots",
    schema=Jackpots,
    get_schema=JackpotBase,
    create_schema=Annotated[JackpotCreate, JsonForm()],
    update_schema=Annotated[JackpotUpdate, JsonForm()],
    filters=Annotated[JackpotFilter, Depends(JackpotFilter)],
    files=Annotated[GameUpload, Depends(GameUpload)]
)


@admin.delete(
    "/jackpots/{game_id}",
    tags=[Action.ADMIN_DELETE],
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.GLOBAL_ADMIN.value,
            Role.ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.SUPPORT.value,
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def delete_jackpot(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
    _type: Literal["delete", "cancel"],
):
    """
    Delete or cancel a jackpot game
    """
    stmt = select(Jackpot).filter(
        Jackpot.id == game_id,
        Jackpot.fund_start <= func.now()
    )
    game = await db.execute(stmt)
    game = game.scalar()
    if not game:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content="Game not found"
        )

    if _type == "delete":
        game.status = GameStatus.DELETED

    if _type == "cancel":
        game.repeat_type = RepeatType.NONE
        game.status = GameStatus.CANCELLED

    try:
        scheduler.remove_job(f"jackpot_{game.id}")
    except JobLookupError:
        pass

    db.add(game)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK, content="Success"
    )


@admin.get(
    "/jackpots/{game_id}/participants",
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.GLOBAL_ADMIN.value,
            Role.ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.SUPPORT.value,
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def get_participants(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
    offset: Optional[int] = 0,
    limit: Optional[int] = 10
):
    """
    Participants and tickets by jackpot ID
    """
    stmt = select(
        User.id,
        User.username,
        func.count(Ticket.id).label("tickets"),
        Ticket.game_id,
        func.min(Ticket.created_at).label("created_at")
    ).join(
        Ticket, User.id == Ticket.user_id
    ).filter(
        Ticket.jackpot_id == game_id
    ).group_by(
        User.id,
        Ticket.game_id
    ).order_by(
        func.min(Ticket.created_at).desc()
    )
    participants = await db.execute(stmt.offset(offset).limit(limit))
    participants = participants.fetchall()

    data = [{
        "id": user.id,
        "username": user.username,
        "tickets": user.tickets,
        "game_id": user.game_id,
        "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for user in participants]

    count_stmt = select(func.count()).select_from(stmt)
    count_result = await db.execute(count_stmt)
    count = count_result.scalar()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"count": count, "data": data}
    )


@admin.get(
    "/jackpots/{game_id}/ticket/{user_id}",
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.GLOBAL_ADMIN.value,
            Role.ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.SUPPORT.value,
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def get_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
    user_id: Annotated[int, Path()],
    offset: Optional[int] = 0,
    limit: Optional[int] = 10
):
    """
    get tickets user by jackpot ID
    """
    stmt = select(Ticket).filter(
        Ticket.jackpot_id == game_id,
        Ticket.user_id == user_id
    )
    tickets = await db.execute(stmt)
    tickets = tickets.scalars().all()

    data = [{
        "id": ticket.id,
        "numbers": ticket.numbers,
    } for ticket in tickets]

    count_stmt = select(func.count()).select_from(stmt)
    count_result = await db.execute(count_stmt)
    count = count_result.scalar()

    return JSONResponse(
        status_code=status.HTTP_200_OK, content={"count": count, "data": data}
    )


@admin.get(
    "/jackpots/{game_id}/winner",
    # dependencies=[Security(
    #     get_admin_token,
    #     scopes=[
    #         Role.SUPER_ADMIN.value,
    #         Role.GLOBAL_ADMIN.value,
    #         Role.ADMIN.value,
    #         Role.LOCAL_ADMIN.value,
    #         Role.SUPPORT.value,
    #     ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def get_winner(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
):
    """
    get winner of jackpot ID
    """
    stmt = select(
        Ticket.id,
        User.username,
        Ticket.numbers
    ).join(
        User, Ticket.user_id == User.id
    ).filter(
        Ticket.jackpot_id == game_id,
        Ticket.won.is_(True)
    )

    winner = await db.execute(stmt)
    winner = winner.scalar()

    data = {
        'id': None,
        'username': None,
        'numbers': None,
    }

    if winner:
        data = {
            "id": winner.id,
            "username": winner.username,
            "numbers": winner.numbers
        }

    tickets_pcs = select(func.count()).filter(
        Ticket.jackpot_id == game_id
    )
    tickets_pcs = await db.execute(tickets_pcs)
    tickets_pcs = tickets_pcs.scalar()

    data["tickets_pcs"] = tickets_pcs

    return JSONResponse(
        status_code=status.HTTP_200_OK, content=data
    )
