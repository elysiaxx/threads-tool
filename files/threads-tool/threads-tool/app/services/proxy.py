"""
Định tuyến outbound qua proxy.

Mô hình "cả hai":
- Account có `proxy_id` -> dùng đúng proxy đó (cố định).
- Account chưa gán -> fallback sang pool xoay vòng (các proxy active của user).

Tất cả bị kiểm soát bởi settings.proxy_enabled (tắt = đi trực tiếp như cũ).
Mật khẩu proxy lưu mã hóa (password_enc); build_proxy_url giải mã đúng lúc dùng.
Hàm nhận sẵn db + user_id để chạy được cả trong route (async) lẫn worker.
"""
import random
from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from urllib.parse import quote

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.core.crypto import decrypt_token
from app.db.repository import TenantRepository


def build_proxy_url(doc: Mapping[str, Any]) -> str:
    """Dựng URL proxy 'proto://user:pass@host:port' (giải mã password)."""
    proto = doc.get("protocol", "http")
    host = doc["host"]
    port = doc["port"]
    auth = ""
    user = doc.get("username")
    if user:
        pw_enc = doc.get("password_enc")
        pw = decrypt_token(pw_enc) if pw_enc else ""
        auth = f"{quote(user, safe='')}:{quote(pw, safe='')}@"
    return f"{proto}://{auth}{host}:{port}"


async def pick_from_pool(
    db: AsyncIOMotorDatabase, user_id: str
) -> Optional[str]:
    """Chọn ngẫu nhiên 1 proxy active của user (pool xoay vòng)."""
    if not settings.proxy_enabled:
        return None
    repo = TenantRepository(db["proxies"], user_id)
    docs = await repo.find_many({"active": True})
    if not docs:
        return None
    return build_proxy_url(random.choice(docs))


async def resolve_for_account(
    db: AsyncIOMotorDatabase, user_id: str, account: Mapping[str, Any]
) -> Optional[str]:
    """Proxy cho 1 account: ưu tiên proxy_id cố định, không có thì lấy từ pool."""
    if not settings.proxy_enabled:
        return None
    repo = TenantRepository(db["proxies"], user_id)
    proxy_id = account.get("proxy_id")
    if proxy_id:
        doc = await repo.find_one({"_id": repo.oid(proxy_id)})
        if doc:
            return build_proxy_url(doc)
    return await pick_from_pool(db, user_id)


async def test_proxy(doc: Mapping[str, Any]) -> dict:
    """Gọi thử tới proxy_test_url qua proxy -> trả {ok, ip, error, checked_at}."""
    now = datetime.now(timezone.utc)
    try:
        url = build_proxy_url(doc)
        async with httpx.AsyncClient(proxy=url, timeout=20) as client:
            resp = await client.get(settings.proxy_test_url)
            resp.raise_for_status()
            try:
                ip = resp.json().get("ip")
            except Exception:  # noqa: BLE001 - body không phải JSON
                ip = resp.text.strip() or None
        return {"ok": True, "ip": ip, "error": None, "checked_at": now}
    except Exception as exc:  # noqa: BLE001 - mọi lỗi mạng/proxy -> báo not ok
        return {"ok": False, "ip": None, "error": str(exc), "checked_at": now}
