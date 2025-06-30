import random
from datetime import datetime
from typing import Annotated

from eth_account import Account
from eth_account.signers.local import LocalAccount
from fastapi import Depends, Request, status, APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.exceptions.user import UserExceptions
from src.globals import aredis
from src.models.db import get_db
from src.models.log import Action
from src.models.user import User, ReferralLink, Wallet
from src.schemes import (
    CheckCode,
    SendCode,
    UserRegister,
    UserLogin,
    AccessToken
)
from src.utils.dependencies import JWTBearer, Token
from src.utils.signature import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

public_auth = APIRouter(tags=["v1.public.auth"])


@public_auth.post(
    "/register",
    tags=[Action.REGISTER],
    responses={200: {"model": AccessToken}}
)
async def register(
    request: Request,
    user: UserRegister,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    if not user.phone_number and not user.username:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Phone number or username is required"}
        )

    if not await aredis.exists(f"AUTH:{request.client.host}"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Please resend sms code"})

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
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "message": "User with this phone number or username already exists"
            },
        )

    if not user_in_db:
        user_in_db = User(
            phone_number=user.phone_number,
            username=user.username,
            country=user.country,
            last_session=datetime.now()
        )
        db.add(user_in_db)
        await db.commit()
        await db.refresh(user_in_db)

        wallet_result = await db.execute(
            select(Wallet)
            .filter(Wallet.user_id == user_in_db.id)
        )
        wallet = wallet_result.scalar()
        if not wallet:

            acc: LocalAccount = Account.create()

            wallet = Wallet(
                user_id=user_in_db.id,
                address=acc.address,
                private_key=acc.key.hex()
            )
            db.add(wallet)
            await db.commit()

            await aredis.sadd("BLOCKER:WALLETS", wallet.address)

        if user.refferal_code:
            refferal = await db.execute(
                select(ReferralLink).filter(
                    ReferralLink.link == user.refferal_code
                )
            )
            refferal = refferal.scalar()

            if refferal:
                user_in_db.referral_id = refferal.id
                refferal.user_count += 1
                db.add(refferal)

        await db.commit()

    data = {
        "id": user_in_db.id,
        "username": user_in_db.username,
        "country": user_in_db.country
    }

    access_token = create_access_token(data=data)
    await aredis.delete(f"AUTH:{request.client.host}")

    await aredis.set(
        f"TOKEN:USERS:{user_in_db.id}",
        access_token,
        ex=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    return {"access_token": access_token, "token_type": "bearer"}


@public_auth.post(
    "/login",
    tags=[Action.LOGIN],
    responses={200: {"model": AccessToken},}
)
async def login(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: UserLogin,
):
    userdb = await db.execute(
        select(User)
        .filter(User.phone_number == user.phone_number)
    )
    userdb = userdb.scalar()
    await UserExceptions.raise_exception_user_not_found(userdb)

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

    data = {
        "id": userdb.id,
        "username": userdb.username,
        "country": userdb.country
    }

    access_token = create_access_token(data=data)

    await aredis.set(
        f"TOKEN:USERS:{userdb.id}",
        access_token,
        ex=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    return {"access_token": access_token, "token_type": "bearer"}


@public_auth.post("/send_code")
async def send_code(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
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

    user_in_db = await db.execute(
        select(User).filter(User.phone_number == item.phone_number)
    )
    user_in_db = user_in_db.scalar()

    if user_in_db:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"type": "Login", "code": code},
        )

    return JSONResponse(
        status_code=200,
        content={"type": "Register", "code": code},
    )


@public_auth.post("/check_code")
async def check_code(
    request: Request,
    item: CheckCode,
):
    """
    Check sms code
    """
    # TODO Непонятно зачем это фронту эта api
    if not await aredis.exists(f"SMS:{request.client.host}"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Invalid code"})

    code: bytes = await aredis.get(f"SMS:{request.client.host}")

    if code.decode("utf-8") != item.code:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Invalid code"}
        )

    await aredis.delete(f"SMS:{request.client.host}")
    await aredis.set(f"AUTH:{request.client.host}", 1, ex=60 * 5)

    return JSONResponse(
        status_code=200,
        content={"message": "Code is correct"}
    )


@public_auth.post(
    "/logout",
    tags=[Action.LOGOUT],
)
async def logout(
    token: Annotated[Token, Depends(JWTBearer())],
):
    """
    Удаление токена из дб
    """
    await aredis.delete(f"TOKEN:USERS:{token.id}")
    return "OK"
