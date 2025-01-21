from fastapi import status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from routers import public
from schemes.tg import WidgetLogin
from utils.signature import TgAuth
from settings import settings


class UserCreate(BaseModel):
    name: str
    email: str


@public.get("/healthcheck")
async def healthcheck():
    return {"status": status.HTTP_200_OK}


@public.post("/tg/login")
async def tg_login(item: WidgetLogin):
    """
        Для логина в telegram mini app
    """
    print(settings.bot_token)
    if not TgAuth(item, settings.bot_token.encode("utf-8")).check_hash():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Bad Request"
        )

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")
