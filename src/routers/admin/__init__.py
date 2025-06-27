import os
from typing import Type, List, Annotated
from fastapi import APIRouter, Depends, Path, status, Security, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, exists, String
from src.models.log import Action
from src.models.other import Game, Ticket

from src.schemes.base import BadResponse
from pydantic import BaseModel
from src.models.db import get_db
from src.models.user import Role
from src.routers import admin
from src.globals import q
from src.utils.dependencies import get_admin_token, Token
from src.schemes.admin import Empty
from src.utils import worker


def get_crud_router(
    model: Type,
    schema: Type[BaseModel],
    get_schema: Type[BaseModel],
    create_schema: Type[BaseModel],
    update_schema: Type[BaseModel],
    filters: Type[BaseModel] = Annotated[Empty, Depends(Empty)],
    files: Type[BaseModel] = Annotated[Empty, Depends(Empty)],
    prefix: str = "",
    security_scopes: List[str] = [
        Role.SUPER_ADMIN.value,
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.SUPPORT.value,
    ],
) -> APIRouter:
    router = admin

    @router.get(
        f"{prefix}",
        responses={200: {"model": schema}},
        name=f"get_{model.__name__}_list",
        dependencies=[Security(get_admin_token, scopes=security_scopes)]
    )
    async def get_items(
        db: Annotated[AsyncSession, Depends(get_db)],
        filters: filters,
        offset: int = 0,
        limit: int = 10,
        model: object = Query(model, include_in_schema=False)
    ):
        model = model

        stmt = select(model)

        if model.__name__ == "Game":

            if filters.game_type:
                stmt = stmt.filter(model.game_type.in_(filters.game_type))

            if filters.category:

                limit_by_ticket = [category.label['limit_by_ticket'] for category in filters.category]
                max_limit_grid = [category.label['max_limit_grid'] for category in filters.category]

                stmt = stmt.filter(
                    model.limit_by_ticket.in_(limit_by_ticket),
                    model.max_limit_grid.in_(max_limit_grid)
                )

            if filters.kind:
                stmt = stmt.filter(model.kind.in_(filters.kind))

            if filters.filter:
                stmt = stmt.filter(
                    or_(
                        func.cast(model.id, String).ilike(f"%{filters.filter}%"),
                        model.name.ilike(f"%{filters.filter}%"),
                    )
                )

            if filters.date_from:
                stmt = stmt.filter(model.created_at >= filters.date_from)

            if filters.date_to:
                stmt = stmt.filter(model.created_at <= filters.date_to)

            has_tickets = exists().where(Ticket.game_id == model.id).label("has_tickets")
            stmt = stmt.add_columns(has_tickets)

        if model.__name__ == "ReferralLink":

            if filters.status:
                deleted = [status.label for status in filters.status]
                stmt = stmt.filter(model.deleted.in_(deleted))

            if filters.filter:
                stmt = stmt.filter(
                    or_(
                        func.cast(model.id, String).ilike(f"%{filters.filter}%"),
                        model.name.ilike(f"%{filters.filter}%"),
                        model.comment.ilike(f"%{filters.filter}%"),
                    )
                )

        if model.__name__ == "Jackpot":

            if filters.filter:
                stmt = stmt.filter(
                    or_(
                        func.cast(model.id, String).ilike(f"%{filters.filter}%"),
                        model.name.ilike(f"%{filters.filter}%"),
                    )
                )

            if filters.date_from:
                stmt = stmt.filter(model.created_at >= filters.date_from)

            if filters.date_to:
                stmt = stmt.filter(model.created_at <= filters.date_to)

            if filters.game_type:
                stmt = stmt.filter(model._type.in_(filters.game_type))

            if filters.countries:
                stmt = stmt.filter(model.country.in_(filters.countries))

            has_tickets = exists().where(Ticket.jackpot_id == model.id).label("has_tickets")
            stmt = stmt.add_columns(has_tickets)

        if model.__name__ == "InstaBingo":
            # avoid None
            stmt = stmt.filter(
                model.country.isnot(None),
                model.deleted.isnot(True)
            )

            if filters.countries:
                stmt = stmt.filter(model.country.in_(filters.countries))

        items = await db.execute(stmt.order_by(model.id.desc()).offset(offset).limit(limit))
        items = items.scalars().all()

        count = await db.execute(stmt.with_only_columns(func.count(model.id)))
        count = count.scalar()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=schema(items=list(items), count=count).model_dump(mode='json')
        )

    @router.get(
        f"{prefix}/{{id}}",
        responses={200: {"model": get_schema}},
        name=f"get_{model.__name__}",
        dependencies=[Security(get_admin_token, scopes=security_scopes)]
    )
    async def get_item(
        db: Annotated[AsyncSession, Depends(get_db)],
        id: Annotated[int, Path()],
    ):
        stmt = select(model).where(model.id == id)

        if model.__name__ == "Game":
            has_tickets = exists().where(Ticket.game_id == model.id).label("has_tickets")
            stmt = stmt.add_columns(has_tickets)

        if model.__name__ == "Jackpot":
            has_tickets = exists().where(Ticket.jackpot_id == model.id).label("has_tickets")
            stmt = stmt.add_columns(has_tickets)

        item = await db.execute(stmt)
        item = item.scalar()

        if not item:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=BadResponse(message=f"{model.__name__} not found").model_dump(mode='json')
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=get_schema.model_validate(item).model_dump(mode='json')
        )

    @router.post(
        f"{prefix}/create",
        tags=[Action.ADMIN_CREATE],
        responses={201: {"model": get_schema}},
        name=f"create_{model.__name__}",
    )
    async def create_item(
        db: Annotated[AsyncSession, Depends(get_db)],
        token: Annotated[Token, Security(get_admin_token, scopes=security_scopes)],
        item: create_schema,
        file: files,
    ):
        new_item = model(**item.model_dump())

        if model.__name__ == "ReferralLink":
            new_item.generated_by = token.id

        if model.__name__ == "InstaBingo":
            stmt = select(model).where(
                model.country == new_item.country,
                model.deleted.is_(False)
            )
            game = await db.execute(stmt)
            game = game.scalar()
            if game:
                raise RequestValidationError(
                    errors=[{
                        "loc": ("body", "country"),
                        "msg": f"Country {new_item.country} already exists",
                        "type": "value_error"
                    }]
                )

        if model.__name__ == "Game":
            file = getattr(file, "image", None)
            if file:
                new_item.image = file
                db.add(new_item)

            q.enqueue_at(
                datetime=new_item.scheduled_datetime,
                f=worker.proceed_game,
                game_id=new_item.id,
                job_id=f"proceed_game_{new_item.id}",
            )

        if model.__name__ == "Jackpot":
            file = getattr(file, "image", None)
            if file:
                new_item.image = file
                db.add(new_item)

            q.enqueue_at(
                new_item.scheduled_datetime,
                getattr(worker, "proceed_jackpot"),
                jackpot_id=new_item.id,
                job_id=f"proceed_jackpot_{new_item.id}",
            )
            q.enqueue_at(
                new_item.fund_start,
                getattr(worker, "set_pending_jackpot"),
                jackpot_id=new_item.id,
                status=GameStatus.PENDING,
                job_id=f"proceed_jackpot_status_{new_item.id}",
            )

        db.add(new_item)
        await db.commit()
        await db.refresh(new_item)

        return get_schema.model_validate(new_item)

    @router.put(
        f"{prefix}/{{id}}/update",
        tags=[Action.ADMIN_UPDATE],
        responses={200: {"model": get_schema}},
        name=f"update_{model.__name__}",
        dependencies=[Security(get_admin_token, scopes=security_scopes)]
    )
    async def update_item(
        db: Annotated[AsyncSession, Depends(get_db)],
        id: Annotated[int, Path()],
        item: update_schema,
        files: files,
    ):
        stmt = select(model).where(model.id == id)
        db_item = await db.execute(stmt)
        db_item = db_item.scalar()
        if not db_item:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=BadResponse(
                    message=f"{model.__name__} not found"
                ).model_dump(mode='json')
            )

        for key, value in item.model_dump().items():
            setattr(db_item, key, value)

        if model.__name__ == "Jackpot":
            if item.scheduled_datetime:
                job = q.fetch_job(f"jackpot_{db_item.id}")
                if job:
                    job.delete()

                q.enqueue_at(
                    item.scheduled_datetime,
                    getattr(worker, "proceed_jackpot"),
                    jackpot_id=db_item.id,
                    job_id=f"jackpot_{db_item.id}",
                )

            if item.fund_start:
                job = q.fetch_job(f"jackpot_status_{db_item.id}")
                if job:
                    job.delete()

                q.enqueue_at(
                    item.fund_start,
                    getattr(worker, "proceed_jackpot_status"),
                    jackpot_id=db_item.id,
                    status=GameStatus.PENDING,
                    job_id=f"jackpot_status_{db_item.id}",
                )

            file = files.image

            if file:
                db_item.image = file

        if model.__name__ == "Game":
            if item.scheduled_datetime:
                job = q.fetch_job(f"game_{db_item.id}")
                if job:
                    job.delete()

                q.enqueue_at(
                    item.scheduled_datetime,
                    worker.proceed_game,
                    game_id=db_item.id,
                    job_id=f"game_{db_item.id}",
                )

            file = files.image

            if file:
                db_item.image = file

        db.add(db_item)
        await db.commit()
        await db.refresh(db_item)

        return get_schema.model_validate(db_item)


from .admins import *
from .auth import *
from .users import *
from .games import *
from .referral import *
from .instabingo import *
from .kyc import *
from .profile import *
from .jackpots import *
from .lobby import *
from .dashboard import *
from .finance import *
