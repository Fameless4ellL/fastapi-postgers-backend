from fastapi import Depends, status
from fastapi.responses import JSONResponse
from typing import Annotated
from models.user import User
from routers import admin
from routers.utils import get_admin
from globals import scheduler


@admin.get("/healthcheck")
async def healthcheck(admin: Annotated[User, Depends(get_admin)]):
    """
    Test endpoint
    """
    return {"status": 200}


@admin.get("/jobs")
async def get_jobs(admin: Annotated[User, Depends(get_admin)]):
    """
    Get active scheduler jobs after game creation(GameInstance)
    """
    jobs = scheduler.get_jobs()
    data = [
        {
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for job in jobs
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data
    )
