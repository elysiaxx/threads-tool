"""
Task nền. NGUYÊN TẮC: mọi task nhận user_id làm tham số để lấy đúng token và
ghi đúng chủ. Job poll định kỳ phải lặp THEO TỪNG user đang active.

Collector, Analytics và Publisher đều đã triển khai.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.db.repository import TenantRepository
from app.services import token_refresh
from app.services.http_retry import TransientError, raise_if_transient
from app.workers.celery_app import celery_app

# Tham số retry chung cho task có gọi mạng: thử lại lỗi tạm thời với lùi thời gian.
_RETRY = dict(
    autoretry_for=(TransientError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=3,
)


def _run(coro):
    """Chạy coroutine; chuyển lỗi mạng/5xx/429 thành TransientError để Celery retry."""
    try:
        return asyncio.run(coro)
    except Exception as exc:  # noqa: BLE001
        raise_if_transient(exc)
        raise


@celery_app.task(name="collector.collect_media", **_RETRY)
def collect_media(user_id: str, source_id: str) -> dict:
    """Tải media của một source (pending) rồi cập nhật trạng thái. Xem collector.service."""
    from app.modules.collector.service import collect_source

    return _run(collect_source(user_id, source_id))


@celery_app.task(name="analytics.poll_account_metrics", **_RETRY)
def poll_account_metrics(user_id: str, account_id: str) -> dict:
    """Poll insights 1 tài khoản owned -> metrics_ts + posts. Xem analytics.service."""
    from app.modules.analytics.service import poll_account

    return _run(poll_account(user_id, account_id))


@celery_app.task(name="analytics.poll_tracked", **_RETRY)
def poll_tracked(user_id: str, keyword_or_account: str) -> dict:
    """Keyword search -> trends. Xem analytics.service."""
    from app.modules.analytics.service import poll_tracked as _poll_tracked

    return _run(_poll_tracked(user_id, keyword_or_account))


# --- Dispatcher cho Celery Beat ---------------------------------------------
# Đây là job CẤP HỆ THỐNG: quét accounts của MỌI user để fan-out poll theo từng
# (user_id, account_id). Vì chạy xuyên tenant nên KHÔNG dùng TenantRepository;
# nó chỉ đọc khóa và enqueue task con (mỗi task con tự scope đúng chủ).
async def _dispatch_owned_accounts() -> int:
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        db = client[settings.mongo_db]
        cursor = db.accounts.find(
            {"type": "owned", "access_token_enc": {"$ne": None}},
            {"_id": 1, "user_id": 1},
        )
        count = 0
        async for acc in cursor:
            poll_account_metrics.delay(acc["user_id"], str(acc["_id"]))
            count += 1
        return count
    finally:
        client.close()


@celery_app.task(name="analytics.dispatch_owned_accounts")
def dispatch_owned_accounts() -> dict:
    """Beat gọi định kỳ: fan-out poll_account_metrics cho mọi owned account."""
    enqueued = asyncio.run(_dispatch_owned_accounts())
    return {"enqueued": enqueued}


@celery_app.task(name="radar.collect_tracked_public", **_RETRY)
def collect_tracked_public(user_id: str) -> dict:
    """Thu thập public posts của watchlist 1 user -> public_posts. Xem trends.service."""
    from app.modules.trends.service import collect_tracked

    return _run(collect_tracked(user_id))


# Dispatcher cấp hệ thống: quét user có tracked account (xuyên tenant) -> fan-out
# collect theo từng user. Dùng distinct user_id để không enqueue trùng.
async def _dispatch_radar() -> int:
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        db = client[settings.mongo_db]
        user_ids = await db.accounts.distinct(
            "user_id", {"type": "tracked", "platform": "threads"}
        )
        for uid in user_ids:
            collect_tracked_public.delay(uid)
        return len(user_ids)
    finally:
        client.close()


@celery_app.task(name="radar.dispatch_tracked")
def dispatch_radar() -> dict:
    """Beat gọi định kỳ: fan-out thu thập public posts cho mọi user có watchlist."""
    return {"enqueued": asyncio.run(_dispatch_radar())}


@celery_app.task(name="publisher.publish", **_RETRY)
def publish(user_id: str, job_id: str) -> dict:
    """Đăng 1 job lên Threads. Xem publisher.service."""
    from app.modules.publisher.service import publish_job

    return _run(publish_job(user_id, job_id))


# Dispatcher cấp hệ thống: quét job 'scheduled' đã tới hạn (xuyên tenant) ->
# đổi sang 'pending' (chống enqueue trùng) rồi đẩy task publish theo đúng chủ.
async def _dispatch_due_jobs() -> int:
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        db = client[settings.mongo_db]
        now = datetime.now(timezone.utc)
        count = 0
        while True:
            job = await db.jobs.find_one_and_update(
                {"status": "scheduled", "scheduled_at": {"$lte": now}},
                {"$set": {"status": "pending", "updated_at": now}},
            )
            if not job:
                break
            publish.delay(job["user_id"], str(job["_id"]))
            count += 1
        return count
    finally:
        client.close()


@celery_app.task(name="publisher.dispatch_due_jobs")
def dispatch_due_jobs() -> dict:
    """Beat gọi định kỳ: enqueue mọi job hẹn giờ đã tới hạn."""
    enqueued = asyncio.run(_dispatch_due_jobs())
    return {"enqueued": enqueued}


# --- Token refresh ----------------------------------------------------------
async def _refresh_one(user_id: str, account_id: str) -> dict:
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        db = client[settings.mongo_db]
        accounts = TenantRepository(db["accounts"], user_id)
        acc = await accounts.find_one({"_id": accounts.oid(account_id)})
        if not acc:
            return {"status": "failed", "error": "account không tồn tại"}
        return await token_refresh.refresh_account(db, user_id, acc)
    finally:
        client.close()


@celery_app.task(name="auth.refresh_account_token", **_RETRY)
def refresh_account_token(user_id: str, account_id: str) -> dict:
    """Gia hạn token cho 1 account owned. Xem services.token_refresh."""
    return _run(_refresh_one(user_id, account_id))


# Dispatcher cấp hệ thống: quét account owned sắp hết hạn (xuyên tenant) ->
# fan-out refresh theo từng (user_id, account_id).
async def _dispatch_token_refresh() -> int:
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        db = client[settings.mongo_db]
        threshold = datetime.now(timezone.utc) + timedelta(
            days=settings.token_refresh_threshold_days
        )
        cursor = db.accounts.find(
            {
                "type": "owned",
                "access_token_enc": {"$ne": None},
                "token_expires_at": {"$lte": threshold},
            },
            {"_id": 1, "user_id": 1},
        )
        count = 0
        async for acc in cursor:
            refresh_account_token.delay(acc["user_id"], str(acc["_id"]))
            count += 1
        return count
    finally:
        client.close()


@celery_app.task(name="auth.dispatch_token_refresh")
def dispatch_token_refresh() -> dict:
    """Beat gọi định kỳ: refresh mọi token sắp hết hạn."""
    return {"enqueued": asyncio.run(_dispatch_token_refresh())}
