from fastapi import Depends, Path, status, Security
from fastapi.responses import JSONResponse
from typing import Annotated

from sqlalchemy import select
from models.user import Role, ReferralLink
from routers import admin
from routers.admin import get_crud_router
from routers.utils import get_admin_token
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import get_db
from schemes.admin import (
    ReferralFilter,
    ReferralSchema,
    Referrals,
    ReferralCreate,
    ReferralUpdate,
)
from schemes.base import BadResponse


get_crud_router(
    model=ReferralLink,
    prefix="/referrals",
    schema=Referrals,
    get_schema=ReferralSchema,
    create_schema=ReferralCreate,
    update_schema=ReferralUpdate,
    filters=Annotated[ReferralFilter, Depends(ReferralFilter)],
    security_scopes=[
        Role.SUPER_ADMIN.value,
        Role.ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.GLOBAL_ADMIN.value,
        Role.SMM.value,
    ],
)


@admin.delete(
    "/referrals/{referral_id}",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])],
    responses={
        400: {"model": BadResponse},
    },
)
async def get_admins(
    db: Annotated[AsyncSession, Depends(get_db)],
    referral_id: Annotated[int, Path(...)]
):
    """
    delete referral
    """
    stmt = select(ReferralLink).filter(ReferralLink.id == referral_id)
    referral = await db.execute(stmt)
    referral = referral.scalar()

    if not referral:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "Referral not found"}
        )

    referral.deleted = True
    db.add(referral)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content="Referral deleted",
    )
