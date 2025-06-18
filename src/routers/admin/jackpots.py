from typing import Annotated, Literal, Optional

from fastapi import Depends, Path, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.exceptions.jackpot import JackpotExceptions
from src.globals import q
from src.models.db import get_db
from src.models.log import Action
from src.models.other import GameStatus, Jackpot, Ticket, RepeatType
from src.models.user import User
from src.routers import admin
from src.routers.admin import get_crud_router
from src.schemes import JsonForm
from src.schemes.admin import (
    GameUpload,
    JackpotBase,
    Jackpots,
    JackpotCreate,
    JackpotUpdate,
    JackpotFilter, JackpotWinner,
)

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
)
async def delete_jackpot(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
    _type: Literal["delete", "cancel"],
):
    """
    Delete or cancel a jackpot game
    """
    stmt = select(Jackpot).filter(Jackpot.id == game_id)
    game = await db.execute(stmt)
    game = game.scalar()

    await JackpotExceptions.raise_exception_user_not_found(game)
    await JackpotExceptions.raise_exception_jackpot_already_started(game)

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


@admin.get("/jackpots/{game_id}/participants")
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
                "id", func.row_number().over(order_by=func.min(Ticket.created_at).desc()),
                "user_id", User.id,
                "username", User.username,
                "tickets", func.count(Ticket.id),
                "game_id", Ticket.game_id,
                "created_at", func.min(Ticket.created_at)
            )
        )
        .select_from(Ticket)
        .join(User, User.id == Ticket.user_id)
        .filter(Ticket.jackpot_id == game_id)
        .group_by(
            User.id,
            Ticket.game_id
        )
        .order_by(func.min(Ticket.created_at).desc())
    )
    count_stmt = select(func.count()).select_from(stmt)
    count_result = await db.execute(count_stmt)
    count = count_result.scalar()

    participants = await db.execute(stmt.offset(offset).limit(limit))
    participants = participants.scalars().all()

    return {"count": count, "data": participants}


@admin.get("/jackpots/{obj_id}/ticket/{user_id}")
async def get_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    obj_id: Annotated[int, Path(ge=0)],
    user_id: Annotated[int, Path(ge=0)],
    game_id: Annotated[Optional[int], Query(ge=0)] = None,
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
            Ticket.jackpot_id == obj_id,
            Ticket.user_id == user_id
        )
        .order_by(Ticket.created_at.desc())
    )
    if game_id:
        stmt = stmt.filter(Ticket.game_id == game_id)

    count_stmt = select(func.count()).select_from(stmt)
    count_result = await db.execute(count_stmt)
    count = count_result.scalar()

    tickets = await db.execute(stmt.offset(offset).limit(limit))
    tickets = tickets.scalars().all()

    return {"count": count, "data": tickets}


@admin.get(
    "/jackpots/{obj_id}/winner",
    responses={200: {"model": JackpotWinner}},
)
async def get_winner(
    db: Annotated[AsyncSession, Depends(get_db)],
    obj_id: Annotated[int, Path(ge=0)],
):
    """
    get winner of jackpot ID
    """
    stmt = select(
        Ticket.id,
        User.id,
        User.username,
        Ticket.numbers
    ).join(
        User, Ticket.user_id == User.id
    ).filter(
        Ticket.jackpot_id == obj_id,
        Ticket.won.is_(True)
    )

    winner = await db.execute(stmt)
    winner = winner.first()

    data = {
        'id': None,
        'user_id': None,
        'username': None,
        'numbers': None,
    }

    if winner:
        ticket_id, user_id, username, numbers = winner
        data = {
            "id": ticket_id,
            "user_id": user_id,
            "username": username,
            "numbers": numbers
        }

    tickets_pcs = select(func.count()).filter(
        Ticket.jackpot_id == obj_id
    )
    tickets_pcs = await db.execute(tickets_pcs)
    tickets_pcs = tickets_pcs.scalar()

    data["tickets_pcs"] = tickets_pcs

    return data
