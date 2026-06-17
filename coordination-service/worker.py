import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from redis import Redis
from rq import Queue, SimpleWorker, Worker

load_dotenv()
_backend_env = Path(__file__).resolve().parent.parent / "backend" / ".env"
if _backend_env.is_file():
    load_dotenv(_backend_env, override=False)

redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
redis_conn = Redis.from_url(redis_url)

if __name__ == "__main__":
    queues = [Queue("dupla_coordination", connection=redis_conn)]
    worker_cls = SimpleWorker if sys.platform == "win32" else Worker
    worker = worker_cls(queues, connection=redis_conn)
    worker.work()
