import secrets
from typing import Annotated

from fastapi import Depends, status, Response
from fastapi.responses import JSONResponse
from httpx import AsyncClient
from passlib.exc import MalformedTokenError, TokenError
from passlib.totp import TOTP
from rq import Retry
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from settings import settings
from src.globals import aredis, TotpFactory, q
from src.models.db import get_db
from src.models.log import Action
from src.models.user import User
from src.routers import admin, public
from src.schemes import AccessToken
from src.schemes.admin import (
    ResetPassword,
    AdminLogin,
    ForgotPassword,
    Totp,
    VerifyLink,
)
from src.utils import worker
from src.utils.dependencies import Token, http_client, get_admin, get_ip, JWTBearerAdmin, Permission, \
    IsNotUser, IsAuthenticated
from src.utils.signature import (
    create_access_token,
    get_password_hash,
    verify_password,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

@public.post(
    "/admin/login",
    tags=["admin", Action.ADMIN_LOGIN],
    responses={200: {"model": AccessToken}},
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


@public.post("/admin/reset", tags=["admin"])
async def set_reset_password(
    db: Annotated[AsyncSession, Depends(get_db)],
    ip: Annotated[str, Depends(get_ip)],
    item: ResetPassword,
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
    user.verified = False
    await db.commit()
    await aredis.delete(f"IP:EMAIL:{ip}")

    q.enqueue(
        worker.send_mail,
        subject="Password Reset",
        body="Your password has been reset successfully",
        to_email=user.email,
        retry=Retry(max=3, interval=[5, 10, 15]),
        job_id=f"reset-password-{user.id}-{secrets.token_urlsafe(16)}",
    )

    return "OK"


@public.post("/admin/registration", tags=["admin"])
async def set_new_user_password(
    db: Annotated[AsyncSession, Depends(get_db)],
    ip: Annotated[str, Depends(get_ip)],
    item: ResetPassword,
):
    return await set_reset_password(db, ip, item)


@public.post("/admin/reset/password", tags=["admin"])
async def send_reset_password(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: ForgotPassword,
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
    await aredis.set(f"EMAIL:{code}", user.email, ex=60 * 15)

    q.enqueue(
        worker.send_mail,
        subject="Восстановление доступа",
        body=(
            f"Здравствуйте, {user.firstname} !\n"
            "Перейдите по ссылке, чтобы сбросить пароль для вашей учетной записи на платформе BINGO :\n"
            f"{settings.web_app_url}/reset-password/{code}"
        ),
        to_email=user.email,
        retry=Retry(max=3, interval=[5, 10, 15]),
        job_id=f"reset-password-{user.id}-{code}",
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content="Email has been sent")


@admin.post(
    "/logout",
    tags=[Action.ADMIN_LOGOUT],
)
async def logout(
    token: Annotated[Token, Depends(JWTBearerAdmin())],
):
    """
    Admin logout
    """
    await aredis.delete(f"TOKEN:ADMINS:{token.id}")

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@public.get(
    "/admin/totp",
    tags=["admin"],
    dependencies=[Depends(Permission([IsNotUser, IsAuthenticated]))]
)
async def get_totp(
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[AsyncClient, Depends(http_client)],
    user: Annotated[User, Depends(get_admin)],
):
    """
    Get TOTP secret
    """
    if user.verified:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "TOTP already verified"}
        )

    totp: TOTP = TotpFactory.new()

    # get image from url
    qrcode = await client.get(
        "https://api.qrserver.com/v1/create-qr-code/?",
        params={
            "size": "300x300",
            "data": totp.to_uri(label=user.username, issuer="Bingo-Admin"),
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        timeout=5
    )

    user.totp = totp.to_json()
    await db.merge(user)
    await db.commit()

    return Response(
        content=qrcode.content,
        media_type="image/png",
        headers={
            "Content-Disposition": "inline; filename=totp.png",
            "Secret": totp.base32_key,
        }
    )


@public.post(
    "/admin/totp",
    tags=["admin"],
    dependencies=[Depends(Permission([IsNotUser, IsAuthenticated]))]
)
async def verify_totp(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Totp,
    user: Annotated[User, Depends(get_admin)],
):
    """
    Verify TOTP
    """
    try:
        TotpFactory.verify(item.code, user.totp)
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

    if not user.verified:
        user.verified = True
        await db.merge(user)
        await db.commit()

    data = {
        "id": user.id,
        "scopes": [user.role],
    }

    access_token = create_access_token(data=data)

    await aredis.set(
        f"TOKEN:ADMINS:{user.id}",
        access_token,
        ex=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    return {"access_token": access_token, "token_type": "bearer"}


@public.post("/admin/verify/link")
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

    email = await aredis.get(f"EMAIL:{item.code}")
    await aredis.set(f"IP:EMAIL:{ip}", email.decode('utf-8'), ex=60 * 10)
    await aredis.delete(f"EMAIL:{item.code}")

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "OK"},
    )
