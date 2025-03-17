import os
from fastapi import Depends, Path, status, Security
from fastapi.responses import JSONResponse
from apscheduler.jobstores.base import JobLookupError
from typing import Annotated, Literal

from sqlalchemy import select, func, orm, exists
from models.user import Role, User
from models.other import Currency, InstaBingo, GameStatus, GameView, Ticket
from routers import admin
from routers.admin import get_crud_router
from routers.utils import get_admin_token
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import get_db, get_sync_db
from schemes.admin import (
    InstaBingoFilter,
    InstaBingoSchema,
    InstaBingos,
    InstaBingoCreate,
    InstaBingoUpdate,
    Empty
)
from globals import scheduler
from schemes.base import BadResponse, JsonForm


get_crud_router(
    model=InstaBingo,
    prefix="/instabingo",
    schema=InstaBingos,
    get_schema=InstaBingoSchema,
    create_schema=InstaBingoCreate,
    update_schema=InstaBingoUpdate,
    files=Annotated[Empty, Depends(Empty)],
    filters=Annotated[InstaBingoFilter, Depends(InstaBingoFilter)],
    security_scopes=[
        Role.SUPER_ADMIN.value,
        Role.ADMIN.value,
        Role.GLOBAL_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ]
)


# @admin.delete(
#     "/games/{game_id}",
#     dependencies=[Security(
#         get_admin_token,
#         scopes=[
#             Role.GLOBAL_ADMIN.value,
#             Role.LOCAL_ADMIN.value,
#             Role.ADMIN.value,
#             Role.SUPER_ADMIN.value
#         ])],
#     responses={
#         400: {"model": BadResponse},
#     },
# )
async def delete_game(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
    _type: Literal["delete", "cancel"],
):
    """
    Get all admins
    """
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