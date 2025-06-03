from typing import Annotated, Literal, Optional

from fastapi import Depends, Path, Security, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.globals import q
from src.models.db import get_db
from src.models.log import Action
from src.models.other import GameStatus, Jackpot, Ticket, RepeatType
from src.models.user import User, Role
from src.routers import admin
from src.routers.admin import get_crud_router
from src.utils.dependencies import get_admin_token
from src.schemes.admin import (
    GameUpload,
    JackpotBase,
    Jackpots,
    JackpotCreate,
    JackpotUpdate,
    JackpotFilter,
)
from src.schemes import BadResponse, JsonForm

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

    job = q.fetch_job(f"jackpot_{game.id}")
    if job:
        job.remove()

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
    stmt = (
        select(
            func.json_build_object(
                "id", User.id,
                "username", User.username,
                "tickets", func.count(Ticket.id),
                "ticket_id", Ticket.id,
                "jackpot_id", Ticket.jackpot_id,
                "created_at", func.min(Ticket.created_at)
            )
        )
        .select_from(User)
        .join(Ticket, User.id == Ticket.user_id)
        .filter( Ticket.jackpot_id == game_id)
        .group_by(
            User.id,
            Ticket.id,
            Ticket.jackpot_id
        )
        .order_by(func.min(Ticket.created_at).desc())
    )
    count_stmt = select(func.count()).select_from(stmt)
    count_result = await db.execute(count_stmt)
    count = count_result.scalar()

    participants = await db.execute(stmt.offset(offset).limit(limit))
    participants = participants.scalars().all()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"count": count, "data": participants}
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
    game_id: Annotated[int, Path(ge=0)],
    user_id: Annotated[int, Path(ge=0)],
    offset: int = 0,
    limit: int = 10
):
    """
    get tickets user by jackpot ID
    """
    stmt = (
        select(
            func.json_build_object(
                "id", Ticket.id,
                "number", Ticket.number,
                "numbers", Ticket.numbers
            )
        )
        .select_from(Ticket)
        .filter(
            Ticket.jackpot_id == game_id,
            Ticket.user_id == user_id
        )
        .order_by(Ticket.created_at.desc())
    )
    count_stmt = select(func.count()).select_from(stmt)
    count_result = await db.execute(count_stmt)
    count = count_result.scalar()

    tickets = await db.execute(stmt.offset(offset).limit(limit))
    tickets = tickets.scalars().all()

    return JSONResponse(
        status_code=status.HTTP_200_OK, content={"count": count, "data": tickets}
    )


@admin.get(
    "/jackpots/{game_id}/winner",
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
    winner = winner.first()

    data = {
        'id': None,
        'username': None,
        'numbers': None,
    }

    if winner:
        ticket_id, username, numbers = winner
        data = {
            "id": ticket_id,
            "username": username,
            "numbers": numbers
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
