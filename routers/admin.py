from fastapi import Depends
from routers import admin
from routers.utils import get_admin


@admin.get("/healthcheck", dependencies=[Depends(get_admin)])
async def healthcheck():
    """
    Test endpoint
    """
    return {"status": 200}
