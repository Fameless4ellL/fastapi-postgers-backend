import datetime
import traceback
from pydantic import BaseModel, ConfigDict
from routers import _cron
from globals import scheduler
from worker.worker import worker


class JobRequest(BaseModel):
    func_name: str
    args: list = []
    run_date: datetime.datetime

    model_config = ConfigDict(arbitrary_types_allowed=True)


@_cron.post("/add_job/", include_in_schema=True)
async def add_job(request: JobRequest):
    try:
        func = getattr(worker, request.func_name, None)
        if not func:
            raise ValueError(f"Function {request.func_name} not found")

        print(request.run_date.strftime("%Y-%m-%d %H:%M:%S"))
        scheduler.add_job(
            func=func,
            trigger="date",
            args=request.args,
            run_date=request.run_date.strftime("%Y-%m-%d %H:%M:%S")
        )
    except Exception:
        traceback.print_exc()
    return {"status": "ok"}