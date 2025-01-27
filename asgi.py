from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routers import public, admin, _cron


fastapp = FastAPI()

fastapp.include_router(public)
fastapp.include_router(admin)
fastapp.include_router(_cron)
fastapp.mount("/static", app=StaticFiles(directory="static"), name="static")

origins = ["*"]

fastapp.add_middleware(
	CORSMiddleware,
	allow_origins=origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)
