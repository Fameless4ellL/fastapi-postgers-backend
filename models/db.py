from aiogram import BaseMiddleware
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from settings import settings


engine = create_async_engine(
    settings.database_url.format(mode="asyncpg"),
    echo=settings.debug,
    future=True
)
sync_engine = create_engine(
    settings.database_url.format(mode="psycopg2"),
    echo=settings.debug,
    future=True
)
Base = declarative_base()


async def get_db():
    async_session = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    async with async_session() as session:
        yield session


def get_sync_db():
    session = sessionmaker(bind=sync_engine)
    return session()


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
        try:
            return await handler(event, data)
        finally:
            if data["db"]:
                await data["db"].close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
