import os
import traceback
import json
import marshal
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from typing import Callable
from globals import redis
from utils import worker


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


WORKER_TASK_KEY = "WORKER:tasks"


def add_to_queue(func_name: str, *args, **kwargs):
    try:
        func_params = {
            "args": args,
            "kwargs": kwargs
        }
        json_params = json.dumps(func_params)

        value = marshal.dumps({
            "func": func_name,
            **json.loads(json_params)
        })

        return redis.lpush(WORKER_TASK_KEY, value)

    except Exception as error:
        print('add_to_queue ERROR:', error)


def process(max_workers: int):
    start_time = datetime.now()
    logger.info(f"Worker started at {start_time}")

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while True:
            try:

                task = redis.brpop(
                    WORKER_TASK_KEY,
                    timeout=60
                )

                if not task:
                    continue

                _, task = task

                task_obj = marshal.loads(task)

                if task_obj["func"] not in worker:
                    raise TypeError(
                        f"Task `{task_obj['func']}` not in whitelist"
                    )

                logger.info(f"Task {task_obj['func']} {task_obj}")

                func = getattr(worker, task_obj["func"], None)

                if not func:
                    raise TypeError(
                        f"function `{task_obj['func']}` not found"
                    )

                pool.submit(build, func, task_obj)

            except TypeError:
                traceback.print_exc()

            except Exception:
                traceback.print_exc()


def build(func: Callable, task: dict):
    try:
        func(*task["args"], **task["kwargs"])
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    process(os.environ.get("MAX_WORKERS", 2))
