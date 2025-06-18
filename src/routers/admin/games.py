from typing import Annotated, Literal

from fastapi import Depends, Path, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, orm, exists, Text
from sqlalchemy.ext.asyncio import AsyncSession

from src.globals import q
from src.models.db import get_db, get_sync_db
from src.models.log import Action
from src.models.other import Currency, Game, GameStatus, GameView, TicketStatus, Ticket
from src.models.user import Role, User
from src.routers import admin
from src.routers.admin import get_crud_router
from src.schemes import JsonForm
from src.schemes.admin import (
    GameFilter,
    GameUpload,
    GameSchema,
    Games,
    GameCreate,
    GameUpdate,
    Winners,
    PurchasedTickets,
    Participant,
    ParticipantTickets,
)
from src.utils.dependencies import Permission, IsSuper, IsAdmin, IsGlobal, IsLocal

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
    dependencies=[Depends(Permission([IsSuper, IsAdmin, IsGlobal, IsLocal]))],
    responses={200: {"description": "Success"}},
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

    job = q.fetch_job(f"game_{game.id}")
    if job:
        job.delete()

    db.add(game)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK, content="Success"
    )


@admin.get(
    "/games/{game_id}/purchased",
    responses={200: {"model": PurchasedTickets}},
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
            'prize': "0",
        }
    else:
        data = {
            'pcs': tickets.pcs,
            'currency': tickets.code,
            'amount': float(tickets.amount),
            'prize': tickets.prize,
        }

    return JSONResponse(
        status_code=status.HTTP_200_OK, content=data
    )


@admin.get(
    "/games/{game_id}/participants",
    responses={200: {"model": list[Participant]}},
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
    responses={200: {"model": list[ParticipantTickets]}},
)
async def get_participant_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path(ge=0)],
    user_id: Annotated[int, Path(ge=0)],
    offset: int = 0,
    limit: int = 10,
):
    """
    get tickets by user_id from game_id
    """
    stmt = select(
        Ticket.id,
        Ticket.user_id,
        Ticket.number,
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
        "number": ticket.number,
        "user": ticket.username,
        "tickets": ticket.numbers,
        "date": ticket.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for ticket in tickets]

    return JSONResponse(
        status_code=status.HTTP_200_OK, content=data
    )


@admin.get(
    "/games/{game_id}/winners",
    responses={200: {"model": Winners}},
)
async def get_winners(
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10,
):
    """
    get winners by game_id
    """
    tickets = (
        select(
            func.json_build_object(
                "id", Ticket.id,
                "user_id", Ticket.user_id,
                "numbers", Ticket.number,
                "status", func.coalesce(func.lower(Ticket.status.cast(Text)), func.lower(Ticket.status.cast(Text))),
                "amount", func.sum(Ticket.amount),
                "created_at", Ticket.created_at,
                "user", User.username,
                "prize", Game.prize
            )
        )
        .select_from(Ticket)
        .join(User, Ticket.user_id == User.id)
        .join(Game, Ticket.game_id == Game.id)
        .filter(
            Ticket.game_id == game_id,
            Ticket.won.is_(True)
        )
        .group_by(
            Ticket.id,
            Ticket.user_id,
            Ticket.number,
            Ticket.status,
            Ticket.created_at,
            User.username,
            Game.prize
        )
    )

    count = (
        select(func.count(Ticket.id))
        .select_from(Ticket)
        .join(Game, Ticket.game_id == Game.id)
        .filter(
            Ticket.game_id == game_id,
            Ticket.won.is_(True)
        )
    )

    count = await db.execute(count)
    count = count.scalar()

    tickets = await db.execute(tickets.offset(offset).limit(limit))
    tickets = tickets.scalars().all()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"count": count, "items": tickets}
    )


@admin.put(
    "/games/{game_id}/winners/{ticket_id}",
    tags=[Action.ADMIN_UPDATE],
    responses={200: {"description": "OK"}},
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

    ticket.status = TicketStatus.COMPLETED
    db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK, content="OK"
    )
