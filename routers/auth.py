import random

from fastapi.security import OAuth2PasswordRequestForm
from phonenumbers import geocoder, parse
from fastapi import Depends, Request, status
from models.db import get_db
from models.user import User
from typing import Annotated, Optional
from routers import public
from fastapi.responses import JSONResponse
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from schemes.auth import SendCode, UserCreate, UserLogin, AccessToken
from schemes.base import BadResponse
from globals import aredis

from utils.signature import create_access_token, verify_password


@public.post(
    "/register",
    tags=["auth"],
    responses={
        400: {"model": BadResponse},
        200: {"model": AccessToken},
    }
)
async def register(
    request: Request,
    user: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    if not user.phone_number and not user.username:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Phone number or username is required"}
        )

    # get country from phone_number
    country_code = parse(user.phone_number)
    country = geocoder.region_code_for_number(country_code)
    phone_number = f"{country_code.country_code}{country_code.national_number}"

    user_in_db = await db.execute(
        select(User).filter(
            or_(User.phone_number == phone_number, User.username == user.username)
        )
    )
    user_in_db = user_in_db.scalar()

    if user_in_db:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "message": "User with this phone number or username already exists"
            },
        )
    if not await aredis.exists(f"SMS:{request.client.host}"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Invalid code"})

    code: bytes = await aredis.get(f"SMS:{request.client.host}")

    if code.decode("utf-8") != user.code:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Invalid code"}
        )

    await aredis.delete(f"SMS:{request.client.host}")

    # hashed_password = get_password_hash(user.password.get_secret_value())
    new_user = User(
        phone_number=phone_number,
        # password=hashed_password,
        username=user.username,
        country=country,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    access_token = create_access_token(
        data={"username": new_user.username, "sub": new_user.phone_number}
    )

    return JSONResponse(
        status_code=200, content={"access_token": access_token, "token_type": "bearer"}
    )


@public.post(
    "/login",
    tags=["auth"],
    responses={
        400: {"model": BadResponse},
        200: {"model": AccessToken},
    }
)
async def login(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: UserLogin,
):
    if not user.phone_number and not user.username:
        return JSONResponse(
            status_code=400, content={"message": "Phone number or username is required"}
        )

    userdb = await db.execute(
        select(User).filter(
            or_(User.phone_number == user.phone_number, User.username == user.username)
        )
    )
    userdb = userdb.scalar()
    if not userdb:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND, content={"message": "User not found"}
        )

    if not await aredis.exists(f"SMS:{request.client.host}"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Invalid code"})

    code: bytes = await aredis.get(f"SMS:{request.client.host}")

    if code.decode("utf-8") != user.code:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Invalid code"}
        )

    await aredis.delete(f"SMS:{request.client.host}")

    # if not user or not verify_password(
    #     user.password.get_secret_value(), userdb.password
    # ):
    #     return JSONResponse(
    #         status_code=400, content={"message": "Invalid phone number or password"}
    #     )

    access_token = create_access_token(
        data={"username": userdb.username, "sub": userdb.phone_number}
    )

    return JSONResponse(
        status_code=200, content={"access_token": access_token, "token_type": "bearer"}
    )


@public.post("/token", include_in_schema=False)
async def token(
    db: Annotated[AsyncSession, Depends(get_db)],
    form: Annotated[OAuth2PasswordRequestForm, Depends(OAuth2PasswordRequestForm)],
):
    if not form.username and not form.password:
        return JSONResponse(
            status_code=400, content={"message": "Phone number or username is required"}
        )

    userdb = await db.execute(
        select(User).filter(
            or_(User.phone_number == form.username, User.username == form.username)
        )
    )
    userdb = userdb.scalar()
    if not userdb:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND, content={"message": "User not found"}
        )

    if not verify_password(form.password, userdb.password):
        return JSONResponse(
            status_code=400, content={"message": "Invalid phone number or password"}
        )

    access_token = create_access_token(
        data={"username": userdb.username, "sub": userdb.phone_number}
    )

    return JSONResponse(
        status_code=200, content={"access_token": access_token, "token_type": "bearer"}
    )


@public.post("/send_code", tags=["auth"])
async def send_code(
    request: Request,
    item: SendCode,
):
    """
    Send sms code on choose phone number 1 min per request from ip
    """
    ip = request.client.host
    if await aredis.exists(f"SMS:{ip}"):
        return JSONResponse(status_code=429, content={"message": "Too many requests"})

    # TODO sent sms code
    code = random.randint(100000, 999999)

    await aredis.set(f"SMS:{ip}", code, ex=60)
    return JSONResponse(
        status_code=200,
        content={"message": "Code sent successfully", "code": code},  # TODO TEMP
    )
