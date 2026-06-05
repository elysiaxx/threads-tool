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

# Beat: định kỳ fan-out poll insights cho mọi owned account (xuyên tenant).
# Mỗi 30 phút — insights cập nhật chậm, tránh đốt rate-limit của Threads API.
celery_app.conf.beat_schedule = {
    "poll-owned-accounts-every-30m": {
        "task": "analytics.dispatch_owned_accounts",
        "schedule": 30 * 60.0,
    },
    # Bài hẹn giờ: quét job tới hạn mỗi phút để đăng đúng lúc.
    "publish-due-jobs-every-1m": {
        "task": "publisher.dispatch_due_jobs",
        "schedule": 60.0,
    },
}

# import để task được đăng ký khi worker khởi động
import app.workers.tasks  # noqa: E402,F401
