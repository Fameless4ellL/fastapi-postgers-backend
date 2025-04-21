from fastapi import Depends, status, Security
from fastapi.responses import JSONResponse
from typing import Annotated

from sqlalchemy import select, insert, delete
from models.log import Action
from models.user import Role, Kyc
from routers import admin
from routers.utils import get_admin_token
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import get_db
from schemes.admin import (
    KycBase,
    KycCreate, KycDelete, KycList,
)
from schemes.base import BadResponse


@admin.get(
    "/kyc",
    # dependencies=[Security(
    #     get_admin_token,
    #     scopes=[
    #         Role.SUPER_ADMIN.value,
    #         Role.ADMIN.value,
    #         Role.GLOBAL_ADMIN.value,
    #         Role.LOCAL_ADMIN.value,
    #         Role.FINANCIER.value,
    #         Role.SUPPORT.value
    #     ])],
    responses={
        400: {"model": BadResponse},
        200: {"model": list[KycBase]}
    },
)
async def get_kyc_list(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Получение список стран для KYC
    """
    stmt = select(Kyc)
    data = await db.execute(stmt)
    data = data.scalars().all()

    data = [{
        "id": item.id,
        "country": item.country
    } for item in data]

    return JSONResponse(
        content=KycList(items=data).model_dump(),
        status_code=status.HTTP_200_OK
    )


@admin.post(
    "/kyc/create",
    tags=[Action.ADMIN_CREATE],
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.ADMIN.value,
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.FINANCIER.value,
            Role.SUPPORT.value
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def create_kyc_list(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: KycCreate
):
    """
    Create KYC country bulk_create
    """
    # check if country already exists in list of countries at item.countries
    stmt = select(Kyc).filter(Kyc.country.in_(item.countries))
    data = await db.execute(stmt)
    data = data.scalars().all()
    if data:
        return JSONResponse(
            content={"message": "Country already exists"},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    # bulk create
    stmt = Kyc.__table__.insert().values([{"country": country} for country in item.countries])
    await db.execute(stmt)
    await db.commit()
    return JSONResponse(
        content={"message": "Countries created successfully"},
        status_code=status.HTTP_200_OK
    )


@admin.delete(
    "/kyc",
    tags=[Action.ADMIN_DELETE],
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.ADMIN.value,
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.FINANCIER.value,
            Role.SUPPORT.value
        ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def detele_kyc_list(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Annotated[KycDelete, Depends(KycDelete)],
):
    """
    delete KYC country bulk_delete
    """
    # check if country already exists in list of countries at item.countries
    stmt = select(Kyc).filter(Kyc.country.in_(item.countries))
    data = await db.execute(stmt)
    data = data.scalars().all()
    if not data:
        return JSONResponse(
            content={"message": "Country not found"},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    stmt = Kyc.__table__.delete().where(Kyc.country.in_(item.countries))
    await db.execute(stmt)
    await db.commit()
    return JSONResponse(
        content={"message": "Countries deleted successfully"},
        status_code=status.HTTP_200_OK
    )


@admin.put(
    "/kyc",
    tags=[Action.ADMIN_UPDATE],
    # dependencies=[Security(
    #     get_admin_token,
    #     scopes=[
    #         Role.SUPER_ADMIN.value,
    #         Role.ADMIN.value,
    #         Role.GLOBAL_ADMIN.value,
    #         Role.LOCAL_ADMIN.value,
    #         Role.FINANCIER.value,
    #         Role.SUPPORT.value
    #     ])],
    responses={
        400: {"model": BadResponse},
    },
)
async def update_kyc_list(
        db: Annotated[AsyncSession, Depends(get_db)],
        item: KycCreate
):
    """
    Обновление списка стран для KYC
    """
    # Удаление всех существующих записей
    await db.execute(delete(Kyc))
    await db.commit()

    # Создание новых записей
    if item.countries:
        stmt = insert(Kyc).values([{"country": country} for country in item.countries])
        await db.execute(stmt)
        await db.commit()

    return JSONResponse(
        content={"message": "KYC list updated successfully"},
        status_code=status.HTTP_200_OK
    )
