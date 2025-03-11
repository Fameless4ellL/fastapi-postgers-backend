import os
from fastapi import Depends, Path, UploadFile, status, Security
from fastapi.responses import JSONResponse
from apscheduler.jobstores.base import JobLookupError
from typing import Annotated, Literal

from sqlalchemy import select, func
from models.user import Role
from models.other import Currency, Game, GameStatus, Ticket
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
from globals import scheduler
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

    if _type == "delete":
        game.deleted = True

    try:
        scheduler.remove_job(f"game_{game.id}")
    except JobLookupError:
        pass

    game.status = GameStatus.CANCELLED

    db.add(game)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK, content="Success"
    )


@admin.post(
    "/games/{game_id}/upload",
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
async def upload_game_image(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
    file: UploadFile
):
    """
    Загрузка документа
    """
    if not file.content_type.startswith("image"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Invalid file type"
        )

    directory = "static"
    os.makedirs(directory, exist_ok=True)

    stmt = select(Game).filter(Game.id == game_id)
    game = await db.execute(stmt)
    game = game.scalar()
    if not game:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, content="Game not found"
        )

    # Delete old file if it exists
    if game.image:
        old_file_path = os.path.join(directory, f"{game.image}#{game_id}")
        if os.path.exists(old_file_path):
            os.remove(old_file_path)

    game.image = file.filename
    db.add(game)
    # Save file to disk
    filename, file_extension = os.path.splitext(file.filename)

    file_path = os.path.join(directory, f"{filename}#{game_id}{file_extension}")
    with open(file_path, "wb") as f:
        f.write(await file.read())

    game.image = file.filename
    db.add(game)
    await db.commit()

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


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
        func.sum(Ticket.amount).label("amount")
    ).join(
        Currency, Ticket.currency_id == Currency.id
    ).filter(
        Ticket.game_id == game_id
    ).group_by(
        Currency.code
    )
    tickets = await db.execute(stmt)
    tickets = tickets.scalars().all()

    if not tickets:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Tickets not found"
        )

    data = []
    total = 0
    for ticket in tickets:
        data.append({
            "currency": ticket.code,
            "amount": float(ticket.amount)
        })
        total += float(ticket.amount)

    data.append({
        "currency": "total",
        "amount": total
    })

    return JSONResponse(
        status_code=status.HTTP_200_OK, content=data
    )
