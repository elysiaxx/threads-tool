from celery import Celery

from app.config import settings

celery_app = Celery(
    "threads_tool",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
)

# import để task được đăng ký khi worker khởi động
import app.workers.tasks  # noqa: E402,F401
