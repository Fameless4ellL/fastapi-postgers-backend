from routers import _cron
from worker.worker import add_to_queue


@_cron.post("/calc/daily")
async def daily():
    add_to_queue("test")
