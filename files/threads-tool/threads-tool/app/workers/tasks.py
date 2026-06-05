"""
Task nền. NGUYÊN TẮC: mọi task nhận user_id làm tham số để lấy đúng token và
ghi đúng chủ. Job poll định kỳ phải lặp THEO TỪNG user đang active.

Đây là stub cho 2 module sắp làm: Collector và Analytics.
"""
from app.workers.celery_app import celery_app


@celery_app.task(name="collector.collect_media")
def collect_media(user_id: str, source_url: str) -> dict:
    # TODO (Collector): tải media (yt-dlp/httpx) -> storage.upload_bytes(user_id, ...)
    #                    -> lấy public URL -> ghi sources qua TenantRepository.
    raise NotImplementedError("Collector chưa triển khai")


@celery_app.task(name="analytics.poll_account_metrics")
def poll_account_metrics(user_id: str, account_id: str) -> dict:
    # TODO (Analytics): gọi insights tài khoản owned -> ghi metrics_ts
    #                   (meta.user_id, meta.post_id).
    raise NotImplementedError("Analytics chưa triển khai")


@celery_app.task(name="analytics.poll_tracked")
def poll_tracked(user_id: str, keyword_or_account: str) -> dict:
    # TODO (Analytics): keyword/hashtag search hoặc tracked account -> trends/metrics_ts.
    raise NotImplementedError("Analytics chưa triển khai")
