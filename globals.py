import os
import redis as _redis


redis = _redis.Redis(host=os.environ.get("REDIS_HOST", "redis"))
