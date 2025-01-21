from routers import admin


@admin.get("/healthcheck")
async def healthcheck():
    return {"status": 200}