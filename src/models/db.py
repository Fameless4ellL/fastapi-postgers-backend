from aiogram import BaseMiddleware
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from settings import settings

engine_kwargs = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,
    "pool_size": 10,
    "max_overflow": 20,
    "pool_timeout": 30,
    "future": True,
}

engine = create_async_engine(
    settings.database_url.format(
        mode="asyncpg",
        database="db",
        user=settings.postgres_user,
        password=settings.postgres_password,
    ),
    # echo=settings.debug,
    **engine_kwargs,
)

sync_engine = create_engine(
    settings.database_url.format(
        mode="psycopg2",
        database="db",
        user=settings.postgres_user,
        password=settings.postgres_password,
    ),
    # echo=settings.debug,
    **engine_kwargs,
)

# Logs database engine and session
logs_engine = create_async_engine(
    settings.database_url.format(
        mode="asyncpg",
        database="logs",
        user=settings.postgres_user,
        password=settings.postgres_password,
    ),
    # echo=settings.debug,
    **engine_kwargs,
)
logs_sync_engine = create_engine(
    settings.database_url.format(
        mode="psycopg2",
        database="logs",
        user=settings.postgres_user,
        password=settings.postgres_password,
    ),
    # echo=settings.debug,
    **engine_kwargs,
)


# Main database Base class
Base = declarative_base()
# Logs database Base class
LogsBase = declarative_base()


async def get_db():
    async_session = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    async with async_session() as session:
        yield session


async def get_logs_db():
    async_session = sessionmaker(
        bind=logs_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    async with async_session() as session:
        yield session


def get_sync_db():
    session = sessionmaker(bind=sync_engine)
    with session() as session:
        yield session


def get_sync_logs_db():
    session = sessionmaker(bind=logs_sync_engine)
    with session() as session:
        yield session


class DBSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler,  # : Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event,  # : Message,
        data  # : Dict[str, Any]
    ):
        async for session in get_db():
            data["db"] = session
            break
        async for logs_session in get_logs_db():
            data["logs_db"] = logs_session
            break
        try:
            return await handler(event, data)
        finally:
            if data["db"]:
                await data["db"].close()
            if data["logs_db"]:
                await data["logs_db"].close()
