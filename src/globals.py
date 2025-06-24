import os

import redis as _redis
import urllib3
from minio import Minio
from passlib.totp import TOTP
from redis.asyncio import Redis as _aredis
from rq import Queue

from settings import settings, aws

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
TotpFactory: TOTP = TOTP.using(
    secrets={"1": settings.twofa_secret},
    issuer="bingo"
)
storage = Minio(
    aws.minio.endpoint,
    access_key=aws.minio.access_key,
    secret_key=aws.minio.secret_key,
    region=aws.region,
    secure=aws.minio.secure,
    http_client=urllib3.ProxyManager(
        "http://minio:9000",
        timeout=urllib3.Timeout.DEFAULT_TIMEOUT,
        retries=urllib3.Retry(
            total=5,
            backoff_factor=0.2,
            status_forcelist=[500, 502, 503, 504],
        ),
    ),
)
