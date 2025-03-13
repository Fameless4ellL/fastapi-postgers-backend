import os
from fastapi import APIRouter, Depends, Path, status, Security, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, exists
from models.other import Game, Ticket
from typing import Type, List, Annotated
from schemes.admin import ReferralFilter, GameFilter
from schemes.base import BadResponse
from pydantic import BaseModel
from models.db import get_db
from models.user import Role
from routers import admin
from globals import scheduler
from utils.workers import add_to_queue
from routers.utils import get_admin_token, Token
from schemes.admin import Empty


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
        Role.LOCAL_ADMIN.value,
        Role.SUPPORT.value,
    ],
    order_by: str = "id"
) -> APIRouter:
    router = admin

    @router.get(
        f"{prefix}",
        responses={
            400: {"model": BadResponse},
            200: {"model": schema}
        },
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
            filters: GameFilter = filters
            model: Game = model

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
                stmt = stmt.filter(model.name.ilike(f"%{filters.filter}%"))

            if filters.date_from:
                stmt = stmt.filter(model.created_at >= filters.date_from)

            if filters.date_to:
                stmt = stmt.filter(model.created_at <= filters.date_to)

            has_tickets = exists().where(Ticket.game_id == model.id).label("has_tickets")
            stmt = stmt.add_columns(has_tickets)

        if model.__name__ == "ReferralLink":
            filters: ReferralFilter = filters

            if filters.status:
                stmt = stmt.filter(model.deleted == filters.status)

            if filters.query:
                stmt = stmt.filter(
                    or_(
                        model.name.ilike(f"%{filters.query}%"),
                        model.comment.ilike(f"%{filters.query}%"),
                    )
                )

        items = await db.execute(stmt.order_by(model.id.desc()).offset(offset).limit(limit))
        items = items.scalars().all()

        count = await db.execute(stmt.with_only_columns(func.count(model.id)))
        count = count.scalar()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=schema(items=[item for item in items], count=count).model_dump(mode='json')
        )

    @router.get(
        f"{prefix}/{{id}}",
        responses={
            400: {"model": BadResponse},
            200: {"model": get_schema}
        },
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
        responses={
            400: {"model": BadResponse},
            201: {"model": get_schema}
        },
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

        db.add(new_item)
        await db.commit()
        await db.refresh(new_item)

        if model.__name__ == "Game":
            if not file.content_type.startswith("image"):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content="Invalid file type"
                )

            directory = "static"
            os.makedirs(directory, exist_ok=True)

            # Delete old file if it exists
            if new_item.image:
                old_file_path = os.path.join(
                    directory,
                    f"{new_item.image}_{new_item.id}"
                )
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)

            # Save file to disk
            filename, file_extension = os.path.splitext(file.filename)
            new_item.image = f"{filename}#{new_item.id}{file_extension}"
            db.add(new_item)

            file_path = os.path.join(
                directory,
                f"{filename}_{new_item.id}{file_extension}"
            )
            with open(file_path, "wb") as f:
                f.write(await file.read())

            scheduler.add_job(
                func=add_to_queue,
                trigger="date",
                id=f"game_{new_item.id}",
                args=["proceed_game", new_item.id],
                run_date=new_item.scheduled_datetime,
            )

        if model.__name__ == "Jackpot":
            scheduler.add_job(
                func=add_to_queue,
                id=f"jackpot_{new_item.id}",
                trigger="date",
                args=["proceed_jackpot", new_item.id],
                run_date=new_item.scheduled_datetime,
            )

        await db.commit()

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=get_schema.model_validate(new_item).model_dump(mode='json')
        )

    @router.put(
        f"{prefix}/{{id}}/update",
        responses={
            400: {"model": BadResponse},
            200: {"model": get_schema}
        },
        # dependencies=[Security(get_admin_token, scopes=security_scopes)]
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
        for key, value in item.model_dump().items():
            setattr(db_item, key, value)

        if model.__name__ == "Game":
            file = files.image

            if file:
                if not file.content_type.startswith("image"):
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content="Invalid file type"
                    )

                directory = "static"
                os.makedirs(directory, exist_ok=True)

                # Delete old file if it exists
                if db_item.image:
                    old_file_path = os.path.join(
                        directory,
                        f"{db_item.image}#{db_item.id}"
                    )
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)

                # Save file to disk
                filename, file_extension = os.path.splitext(file.filename)
                db_item.image = f"{filename}#{db_item.id}{file_extension}"

                file_path = os.path.join(
                    directory,
                    f"{filename}#{db_item.id}{file_extension}"
                )
                with open(file_path, "wb") as f:
                    f.write(await file.read())

        db.add(db_item)
        await db.commit()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=get_schema.model_validate(db_item).model_dump(mode='json')
        )


from .admins import *
from .auth import *
from .users import *
from .games import *
from .referral import *
# from .instabingo import *
