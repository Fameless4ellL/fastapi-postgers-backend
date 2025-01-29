from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routers import public, admin
from globals import scheduler


@asynccontextmanager
async def lifespan(*args, **kwargs):
    try:
        scheduler.start()
        yield
    finally:
        scheduler.shutdown()


fastapp = FastAPI(lifespan=lifespan)

fastapp.include_router(public)
fastapp.include_router(admin)
fastapp.mount("/static", app=StaticFiles(directory="static"), name="static")

origins = ["*"]

fastapp.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
