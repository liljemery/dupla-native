import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from redis import Redis
from rq import Queue, SimpleWorker, Worker

load_dotenv()
# APS creds live in backend/.env in local dev
_backend_env = Path(__file__).resolve().parent.parent / "backend" / ".env"
if _backend_env.is_file():
    load_dotenv(_backend_env, override=False)


def _configure_logging() -> None:
    """Surface pipeline INFO logs (vision, partidas, takeoffs, budget) in the
    worker console. They use logging.getLogger(...).info(); without an INFO root
    handler they are dropped while only model_derivative's print() output shows.
    """
    level_name = (os.getenv("DUPLA_LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", "%H:%M:%S")
        )
        root.addHandler(handler)
    # Quiet noisy HTTP/SDK loggers so the OpenAI/takeoff lines stay readable.
    for noisy in ("httpx", "httpcore", "urllib3", "openai", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_configure_logging()

redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
redis_conn = Redis.from_url(redis_url)

if __name__ == "__main__":
    queues = [Queue("dupla_processing", connection=redis_conn)]
    worker_cls = SimpleWorker if sys.platform == "win32" else Worker
    worker = worker_cls(queues, connection=redis_conn)
    worker.work()
