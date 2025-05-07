import datetime
import json
import logging
import time
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from httpx import AsyncClient

from models.log import Action, RequestLog, UserActionLog
from routers import public, admin, _cron
from models.db import get_logs_db
from settings import settings
from utils.signature import decode_access_token


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("LOGS")

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
if settings.debug:
    console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
log.addHandler(console_handler)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, AsyncClient]]:
    async with AsyncClient() as client:
        yield {"client": client}


fastapp = FastAPI(lifespan=lifespan)

fastapp.include_router(public)
fastapp.include_router(admin)
fastapp.include_router(_cron)
fastapp.mount("/static", app=StaticFiles(directory="static"), name="static")

origins = ['*']

fastapp.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@fastapp.middleware("http")
async def logger(
    request: Request,
    call_next,
):
    json_body = {}
    if request.headers.get("Content-Type") == "application/json":
        try:
            json_body = await request.json()
        except json.JSONDecodeError:
            pass

    if request.url.path == "/docs" or request.url.path == "/redoc" or request.url.path.startswith("/static"):
        return await call_next(request)

    start = time.perf_counter()

    async for db in get_logs_db():
        try:
            response = await call_next(request)
        except Exception as e:
            request_log = RequestLog(
                method=request.method,
                headers=dict(request.headers),
                body=json_body,
                response=str(e),
                url=request.url.path,
                status_code=500,
                response_time=time.perf_counter() - start
            )
            db.add(request_log)
            await db.commit()
            raise e

        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        try:
            body = json.loads(response_body)
        except json.JSONDecodeError:
            body = response_body.decode("utf-8")
        except Exception as e:
            body = {"error": str(e)}

        request_log = RequestLog(
            method=request.method,
            headers=dict(request.headers),
            body=json_body,
            response=body,
            url=request.url.path,
            status_code=response.status_code,
            response_time=time.perf_counter() - start
        )
        db.add(request_log)
        await db.commit()

        log.debug(f"{request.method} {request.url.path} {response.status_code} {time.perf_counter() - start:.2f}s")
        log.debug(f"Request: {json_body}")
        log.debug(f"Response: {body}")

        actions = set(Action)

        for route in request.app.routes:
            if isinstance(request_log.response, str):
                continue

            if route.path != request.url.path:
                continue

            tags = getattr(route, "tags", [])
            action = next((tag for tag in tags if tag in actions), None)
            if not action:
                action = Action.OTHER

            token = None

            if action in {Action.LOGIN, Action.REGISTER, Action.ADMIN_LOGIN}:
                token = request_log.response.get("access_token")
            else:
                token = request.headers.get("Authorization", "").split(" ")[-1]

            if not token:
                continue

            payload = decode_access_token(token)

            if not payload:
                continue

            user_id = payload.get("id", "")
            scope = payload.get("scopes", [])

            if not user_id or scope:
                continue

            user_action_log = UserActionLog(
                user_id=user_id,
                action=action,
                request_id=request_log.id,
                timestamp=datetime.datetime.now()
            )
            db.add(user_action_log)
            await db.commit()

            log.info(f"User {user_id} did {action}")

        new_response = Response(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type
        )

        return new_response
