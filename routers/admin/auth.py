from fastapi import Depends, Security, background, status
from fastapi.responses import JSONResponse
from typing import Annotated

from sqlalchemy import select, or_
from models.log import Action
from models.user import User, Role
from routers import admin
from routers.utils import Token, get_admin_token, send_mail
from globals import aredis
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import get_db
from schemes.admin import (
    ResetPassword,
    AdminLogin,
)
from schemes.auth import AccessToken
from schemes.base import BadResponse
from utils.signature import (
    create_access_token,
    get_password_hash,
    verify_password,
    ACCESS_TOKEN_EXPIRE_MINUTES
)


@admin.post(
    "/login",
    tags=[Action.ADMIN_LOGIN],
    responses={
        400: {"model": BadResponse},
        200: {"model": AccessToken},
    },
)
async def login(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminLogin,
):
    """
    Admin login
    """
    stmt = select(User).filter(
        or_(
            User.email == user.login,
            User.username == user.login
        ),
        User.role != "user",
        User.active.is_(True)
    )
    userdb = await db.execute(stmt)
    userdb = userdb.scalar()
    if not userdb:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "User not found"}
        )

    if not verify_password(
        user.password.get_secret_value(), userdb.password
    ):
        return JSONResponse(
            status_code=400,
            content={"message": "Invalid phone number or password"}
        )

    data = {
        "id": userdb.id,
        "scopes": [userdb.role],
    }

    access_token = create_access_token(data=data)

    await aredis.set(
        f"TOKEN:ADMINS:{userdb.id}",
        access_token,
        ex=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    return JSONResponse(
        status_code=200,
        content={"access_token": access_token, "token_type": "bearer"}
    )


@admin.post(
    "/reset",
    responses={
        400: {"model": BadResponse},
    },
)
async def reset_password(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: ResetPassword,
    bg: background.BackgroundTasks,
):
    """
    Reset password
    """
    stmt = select(User).filter(
        User.email == item.email,
        User.role != "user",
    )
    user = await db.execute(stmt)
    user = user.scalar()

    if not user:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "User not found"},
        )

    if not await aredis.exists(f"EMAIL:{user.email}"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Code expired"},
        )

    code = await aredis.get(f"EMAIL:{user.email}")
    if code.decode('utf-8') != item.code:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Invalid code"},
        )

    hashed_password = get_password_hash(item.password.get_secret_value())
    user.password = hashed_password
    await db.commit()

    bg.add_task(
        send_mail,
        "Password Reset",
        "Your password has been reset",
        user.email,
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@admin.post(
    "/logout",
    tags=[Action.ADMIN_LOGOUT],
    responses={
        400: {"model": BadResponse},
    },
)
async def logout(
    token: Annotated[Token, Security(get_admin_token, scopes=[
        Role.SUPER_ADMIN.value,
        Role.ADMIN.value,
        Role.GLOBAL_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ])],
):
    """
    Admin logout
    """
    await aredis.delete(f"TOKEN:ADMINS:{token.id}")

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")
