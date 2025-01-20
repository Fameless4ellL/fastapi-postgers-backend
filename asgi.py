from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from models.db import init_db
from routers import router as router_v1


@asynccontextmanager
async def lifespam():
	await init_db()
	yield
	# await shutdown_db()


fastapp = FastAPI()

fastapp.include_router(router_v1)

origins = ["*"]

fastapp.add_middleware(
	CORSMiddleware,
	allow_origins=origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)
