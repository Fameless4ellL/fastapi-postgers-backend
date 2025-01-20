from fastapi import Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User
from models.db import get_db
from routers import router


class UserCreate(BaseModel):
    name: str
    email: str


@router.get("/healthcheck")
async def healthcheck():
    return {"status": status.HTTP_200_OK}


@router.post("/users")
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    new_user = User(name=user.name, email=user.email)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.get("/users/{user_id}")
async def read_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    return user
