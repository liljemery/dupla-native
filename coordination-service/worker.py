import sys

from redis import Redis
from rq import Queue, SimpleWorker, Worker

from runtime_paths import default_redis_url, load_project_env

load_project_env()

redis_conn = Redis.from_url(default_redis_url())

if __name__ == "__main__":
    queues = [Queue("dupla_coordination", connection=redis_conn)]
    worker_cls = SimpleWorker if sys.platform == "win32" else Worker
    worker = worker_cls(queues, connection=redis_conn)
    worker.work()
