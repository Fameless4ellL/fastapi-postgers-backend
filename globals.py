import os
import redis as _redis
from redis.asyncio import Redis as _aredis


redis = _redis.Redis(host=os.environ.get("REDIS_HOST", "redis"))
aredis = _aredis(host=os.environ.get("REDIS_HOST", "redis"))
