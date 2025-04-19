import os
import redis as _redis
from redis.asyncio import Redis as _aredis
from rq import Queue


redis = _redis.Redis(host=os.environ.get("REDIS_HOST", "redis"))
aredis = _aredis(
    host=os.environ.get("REDIS_HOST", "redis"),
    socket_connect_timeout=5,
    socket_keepalive=True,
    health_check_interval=30,
    # decode_responses=True,
    retry_on_timeout=True,
    max_connections=20,
)
q = Queue(connection=redis)
