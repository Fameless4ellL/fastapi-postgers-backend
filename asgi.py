from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from models.db import init_db
from routers import public, admin


@asynccontextmanager
async def lifespan_db(*args, **kwargs):
	await init_db()
	yield
	# await shutdown_db()


fastapp = FastAPI(lifespan=lifespan_db)

fastapp.include_router(public)
fastapp.include_router(admin)

origins = ["*"]

fastapp.add_middleware(
	CORSMiddleware,
	allow_origins=origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)
