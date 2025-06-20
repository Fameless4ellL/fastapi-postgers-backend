import json
import logging
import time
from contextlib import suppress
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.models import RequestLog, get_logs_db, Action, UserActionLog
from src.utils import decode_access_token

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("LOGS")


class RequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        json_body = {}
        if request.headers.get("Content-Type") == "application/json":
            with suppress(json.JSONDecodeError):
                json_body = await request.json()

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

            body = await self.get_body(response)

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
            await self.log_action(request, request_log, db)

        return response

    @staticmethod
    async def log_action(
        request: Request,
        request_log: RequestLog,
        db: AsyncSession
    ):
        route = next(
            (
                route
                for route in request.app.routes
                if (
                    not isinstance(request_log.response, str)
                    and route.path == request.url.path
                    and next(iter(route.methods), "") == request.method
                )
            ),
            None
        )
        if not route:
            return

        tags = getattr(route, "tags", [])
        actions = set(Action)
        action = next((tag for tag in tags if tag in actions), None)
        if not action:
            action = Action.OTHER

        if action in {Action.LOGIN, Action.REGISTER, Action.ADMIN_LOGIN}:
            token = request_log.response.get("access_token")
        else:
            token = request.headers.get("Authorization", "").split(" ")[-1]

        if not token:
            return
        payload = decode_access_token(token)

        if not payload:
            return

        user_id = payload.get("id", "")
        scope = payload.get("scopes", [])

        if not user_id or scope:
            return

        user_action_log = UserActionLog(
            user_id=user_id,
            action=action,
            request_id=request_log.id,
            timestamp=datetime.now()
        )
        db.add(user_action_log)
        await db.commit()

        log.info(f"User {user_id} did {action}")

    @staticmethod
    async def get_body(response: Response):
        try:
            body = json.loads(response.body)
        except json.JSONDecodeError:
            body = response.body.decode("utf-8")
        except Exception as e:
            body = {"error": str(e)}
        return body
