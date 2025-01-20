from aiogram import BaseMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@db/postgres"

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()


async def get_db():
    async with async_session() as session:
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
        try:
            return await handler(event, data)
        finally:
            if data["db"]:
                await data["db"].close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
