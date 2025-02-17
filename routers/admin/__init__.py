from fastapi import APIRouter, Depends, Path, status, Security
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Type, List, Annotated
from schemes.base import BadResponse
from pydantic import BaseModel
from models.db import get_db
from models.user import Role
from routers import admin
from routers.utils import get_admin_token


def get_crud_router(
    model: Type,
    schema: Type[BaseModel],
    get_schema: Type[BaseModel],
    create_schema: Type[BaseModel],
    update_schema: Type[BaseModel],
    prefix: str = "",
    security_scopes: List[str] = [Role.GLOBAL_ADMIN.value]
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
        offset: int = 0,
        limit: int = 10,
    ):
        stmt = select(model)
        items = await db.execute(stmt.offset(offset).limit(limit))
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
            200: {"model": schema}
        },
        dependencies=[Security(get_admin_token, scopes=security_scopes)]
    )
    async def get_item(
        db: Annotated[AsyncSession, Depends(get_db)],
        id: Annotated[int, Path()],
    ):
        stmt = select(model).where(model.id == id)
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
            201: {"model": schema}
        },
        dependencies=[Security(get_admin_token, scopes=security_scopes)]
    )
    async def create_item(
        db: Annotated[AsyncSession, Depends(get_db)],
        item: create_schema
    ):
        new_item = model(**item.model_dump())
        db.add(new_item)
        await db.commit()
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=get_schema.model_validate(new_item).model_dump(mode='json')
        )

    @router.put(
        f"{prefix}/{{id}}/update",
        responses={
            400: {"model": BadResponse},
            200: {"model": schema}
        },
        dependencies=[Security(get_admin_token, scopes=security_scopes)]
    )
    async def update_item(
        db: Annotated[AsyncSession, Depends(get_db)],
        id: Annotated[int, Path()],
        item: update_schema
    ):
        stmt = select(model).where(model.id == id)
        db_item = await db.execute(stmt)
        db_item = db_item.scalar()
        for key, value in item.model_dump().items():
            setattr(db_item, key, value)
        await db.commit()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=get_schema.model_validate(db_item).model_dump(mode='json')
        )


from .admins import *
from .auth import *
from .users import *
