import os
import redis as _redis
from utils.decorator import Worker


redis = _redis.Redis(host=os.environ.get("REDIS_HOST", "redis"))
worker = Worker()
