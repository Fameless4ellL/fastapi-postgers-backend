import os
import redis as _redis
from redis.asyncio import Redis as _aredis
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler


redis = _redis.Redis(host=os.environ.get("REDIS_HOST", "redis"))
aredis = _aredis(host=os.environ.get("REDIS_HOST", "redis"))
jobstores = {
    "default": RedisJobStore(
        host=os.environ.get("REDIS_HOST", "redis"),
        port=6379,
        db=0,
    )
}
scheduler = AsyncIOScheduler(jobstores=jobstores)
