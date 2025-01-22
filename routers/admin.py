from fastapi import Depends, HTTPException
from sqlalchemy import select
from routers import admin
from models.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User


async def get_user(
    telegram_id: int,
    db: AsyncSession = Depends(get_db)
) -> User:
    result = await db.execute(
        select(User).filter(User.telegram_id == telegram_id)
    )
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@admin.get("/healthcheck", dependencies=[Depends(get_user)])
async def healthcheck():
    return {"status": 200}
