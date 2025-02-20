import json
import os
import time
from functools import lru_cache

from redis import Redis

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")


def lru_with_ttl(ttl_seconds, maxsize=128):
    """
    A decorator to apply LRU in-memory cache to a function with defined maximum(!) TTL in seconds.
    Be design an actual TTL may be shorter then the passed value (in rare randomized cases). But it can't be higher.
    :param ttl_seconds: TTL for a cache record in seconds
    :param maxsize: Maximum size of the LRU cache (a functools.lru_cache argument)
    :return: decorated function
    """

    def deco(foo):
        @lru_cache(maxsize=maxsize)
        def cached_with_ttl(*args, ttl_hash, **kwargs):
            return foo(*args, **kwargs)

        def inner(*args, **kwargs):
            return cached_with_ttl(*args, ttl_hash=round(time.time() / ttl_seconds), **kwargs)

        return inner

    return deco


class RedisManager:
    """A class to simplify working with redis"""

    def __init__(self):
        self.redis = Redis(host=REDIS_HOST, port=REDIS_PORT)
        pass

    def exists(self, *keys):
        try:
            return self.redis.exists(*keys)
        except Exception as error:
            print('REDIS exists', error)

    def get_networks(self):
        return json.loads(self.redis.get("BLOCKER:NET"))

    def get_state(self, net_label: str):
        return self.redis.get("BLOCKER:STATE:" + net_label)

    def set_state(self, net_label: str, state: int):
        self.redis.set("BLOCKER:STATE:" + net_label, state)

    @lru_with_ttl(60)
    def get_tokens(self, net_label: str):
        return set(map(lambda x: x.decode("utf-8"), self.redis.smembers("BLOCKER:ERC20:" + net_label)))

    @lru_with_ttl(60)
    def get_wallets(self):
        return set(map(lambda x: x.decode("utf-8"), self.redis.smembers("BLOCKER:WALLETS")))

    @lru_with_ttl(3600)
    def get_event_key(self):
        return self.redis.get("EVENT_KEY").decode("utf-8")


redis_m = RedisManager()
