from fastapi import Depends
from models.db import get_db
from models.user import User
from typing import Annotated
from routers import public
from fastapi.responses import JSONResponse
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from schemes.auth import UserCreate, UserLogin

from utils.signature import (
    create_access_token,
    get_password_hash,
    verify_password
)


@public.post(
    "/register",
    tags=["auth"]
)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
    user_in_db = await db.execute(
        select(User)
        .filter(or_(
            User.phone_number == user.phone_number,
            User.username == user.username
        ))
    )
    user_in_db = user_in_db.scalar()
    if user_in_db:
        return JSONResponse(
            status_code=400,
            content={"message": "User with this phone number or username already exists"}
        )

    hashed_password = get_password_hash(user.password.get_secret_value())
    new_user = User(
        phone_number=user.phone_number,
        password=hashed_password,
        username=user.username
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return JSONResponse(
        status_code=201,
        content={"message": "User registered successfully"}
    )


@public.post(
    "/login",
    tags=["auth"]
)
async def login(
    user: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    userdb = await db.execute(
        select(User)
        .filter(or_(
            User.phone_number == user.phone_number,
            User.username == user.username
        ))
    )
    userdb = userdb.scalar()

    if not user or not verify_password(
        user.password.get_secret_value(),
        userdb.password
    ):
        return JSONResponse(
            status_code=400,
            content={"message": "Invalid phone number or password"}
        )

    access_token = create_access_token(
        data={
            "username": user.username,
            "sub": user.phone_number
        })

    return JSONResponse(
        status_code=200,
        content={"access_token": access_token, "token_type": "bearer"}
    )
