import secrets
from typing import Annotated

from fastapi import Depends, Security, background, status, Response
from fastapi.responses import JSONResponse
from httpx import AsyncClient
from passlib.exc import MalformedTokenError, TokenError
from passlib.totp import TOTP
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from globals import aredis, TotpFactory
from models.db import get_db
from models.log import Action
from models.user import User, Role
from routers import admin
from routers.utils import Token, get_admin_token, send_mail, http_client, get_admin, get_ip
from schemes.admin import (
    ResetPassword,
    AdminLogin,
    ForgotPassword,
    Totp,
    VerifyLink,
)
from schemes.auth import AccessToken
from schemes.base import BadResponse
from settings import settings
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
        "scopes": ["auth"],
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
async def get_reset_password(
    db: Annotated[AsyncSession, Depends(get_db)],
    ip: Annotated[str, Depends(get_ip)],
    item: ResetPassword,
    bg: background.BackgroundTasks,
):
    """
    Reset password
    """
    email = await aredis.get(f"IP:EMAIL:{ip}")
    if not email:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "link expired"},
        )

    stmt = select(User).filter(
        User.email == email.decode('utf-8'),
        User.role != "user",
    )
    user = await db.execute(stmt)
    user = user.scalar()

    if not user:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "User not found"},
        )

    if user.password == item.password.get_secret_value():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "New password is the same as old password"},
        )

    hashed_password = get_password_hash(item.password.get_secret_value())
    user.password = hashed_password
    await db.commit()
    await aredis.delete(f"IP:EMAIL:{ip}")

    bg.add_task(
        send_mail,
        "Password Reset",
        "Your password has been reset",
        user.email,
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@admin.post(
    "/reset/password",
    responses={
        400: {"model": BadResponse},
    },
)
async def send_reset_password(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: ForgotPassword,
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
            content={"message": "Email is not valid"},
        )

    code = secrets.token_urlsafe(16)
    await aredis.set(f"EMAIL:{code}", user.email, ex=300)

    bg.add_task(
        send_mail,
        "Восстановление доступа",
        (
            f"Здравствуйте, {user.firstname} !"
            "Перейдите по ссылке, чтобы сбросить пароль для вашей учетной записи на платформе BINGO :"
            f" {settings.web_app_url}/reset-password/{code}"
        ),
        user.email,
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content="Email has been sent")


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
        Role.SUPPORT.value,
        "auth"
    ])],
):
    """
    Admin logout
    """
    await aredis.delete(f"TOKEN:ADMINS:{token.id}")

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@admin.get(
    "/totp",
    responses={
        400: {"model": BadResponse},
    },
)
async def get_totp(
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[AsyncClient, Depends(http_client)],
    admin: Annotated[User, Security(get_admin, scopes=[
        Role.SUPER_ADMIN.value,
        Role.ADMIN.value,
        Role.GLOBAL_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value,
        "auth"
    ])],
):
    """
    Get TOTP secret
    """
    totp: TOTP = TotpFactory.new()

    # get image from url
    qrcode = await client.get(
        "https://api.qrserver.com/v1/create-qr-code/?",
        params={
            "size": "300x300",
            "data": totp.to_uri(label=admin.username, issuer="Bingo-Admin"),
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        timeout=5
    )

    admin.totp = totp.to_json()
    await db.merge(admin)
    await db.commit()

    return Response(
        content=qrcode.content,
        media_type="image/png",
        headers={
            "Content-Disposition": "inline; filename=totp.png",
            "Secret": totp.base32_key,
        }
    )


@admin.post(
    "/totp",
    responses={
        400: {"model": BadResponse},
    },
)
async def verify_totp(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Totp,
    admin: Annotated[User, Security(get_admin, scopes=[
        Role.SUPER_ADMIN.value,
        Role.ADMIN.value,
        Role.GLOBAL_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value,
        "auth"
    ])]
):
    """
    Verify TOTP
    """
    if admin.totp and admin.verified:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "TOTP already verified"}
        )

    try:
        TotpFactory.verify(item.code, admin.totp)
    except MalformedTokenError as err:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": str(err)}
        )
    except TokenError as err:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": str(err)}
        )

    admin.verified = True
    await db.merge(admin)
    await db.commit()

    data = {
        "id": admin.id,
        "scopes": [admin.role],
    }

    access_token = create_access_token(data=data)

    await aredis.set(
        f"TOKEN:ADMINS:{admin.id}",
        access_token,
        ex=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    return JSONResponse(
        status_code=200,
        content={"access_token": access_token, "token_type": "bearer"}
    )


@admin.post(
    "/verify/link",
    include_in_schema=False,
    responses={
        400: {"model": BadResponse},
    },
)
async def verify_link(
    ip: Annotated[str, Depends(get_ip)],
    item: VerifyLink,
):
    """
    Verify link
    """
    if not await aredis.exists(f"EMAIL:{item.code}"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "link expired"},
        )

    await aredis.set(f"IP:EMAIL:{ip}", item.email, ex=300)
    await aredis.delete(f"EMAIL:{item.code}")

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "OK"},
    )
