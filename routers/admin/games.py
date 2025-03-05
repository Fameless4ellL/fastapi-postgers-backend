from fastapi import Depends, Path, status, Security
from fastapi.responses import JSONResponse
from typing import Annotated, Literal

from sqlalchemy import select
from models.user import Role
from models.other import Game, GameStatus
from routers import admin
from routers.admin import get_crud_router
from routers.utils import get_admin_token
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import get_db
from schemes.admin import (
    GameFilter,
    GameSchema,
    Games,
    GameCreate,
    GameUpdate,
)
from schemes.base import BadResponse


get_crud_router(
    model=Game,
    prefix="/games",
    schema=Games,
    get_schema=GameSchema,
    create_schema=GameCreate,
    update_schema=GameUpdate,
    filters=Annotated[GameFilter, Depends(GameFilter)],
    security_scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.GLOBAL_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ]
)


@admin.delete(
    "/games/{game_id}",
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
async def get_admin_(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
    _type: Literal["deleted", "cancel"],
):
    """
    Get all admins
    """
    stmt = select(Game).filter(Game.id == game_id)
    game = await db.execute(stmt)
    if not game:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content="Game not found"
        )

    if _type == "deleted":
        game.deleted = True

    game.status = GameStatus.CANCELLED
    db.add(game)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK, content="Success"
    )
