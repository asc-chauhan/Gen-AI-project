import os
from redis import Redis
from rq import Queue

REDIS_URL = os.environ.get("REDIS_URL", "redis://valkey:6379")

redis_connection = Redis.from_url(REDIS_URL)
queue = Queue(connection=redis_connection)