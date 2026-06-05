"""
Phân loại lỗi outbound: tạm thời (mạng / 5xx / 429) thì nên để Celery retry;
lỗi terminal (4xx, dữ liệu sai…) thì ghi failed và dừng.

Service bọc lỗi tạm thời thành TransientError rồi re-raise; task khai báo
autoretry_for=(TransientError,) + retry_backoff để thử lại có lùi thời gian.
"""
import httpx

_RETRY_STATUS = {429, 500, 502, 503, 504}


class TransientError(Exception):
    """Lỗi tạm thời nên thử lại (Celery autoretry sẽ bắt loại này)."""


def is_transient(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRY_STATUS
    return False


def raise_if_transient(exc: Exception) -> None:
    """Re-raise dưới dạng TransientError nếu là lỗi tạm thời; ngược lại không làm gì."""
    if is_transient(exc):
        raise TransientError(str(exc)) from exc
