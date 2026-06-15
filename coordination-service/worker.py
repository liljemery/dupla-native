import os
from redis import Redis
from rq import Worker, Queue
from dotenv import load_dotenv

load_dotenv()

redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
redis_conn = Redis.from_url(redis_url)

if __name__ == "__main__":
    queues = [Queue("dupla_coordination", connection=redis_conn)]
    worker = Worker(queues, connection=redis_conn)
    worker.work()
