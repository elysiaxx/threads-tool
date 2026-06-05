"""
Gia hạn access token Threads trước khi hết hạn (~60 ngày). Dùng bởi task định
kỳ (Beat quét account sắp hết hạn) và endpoint refresh thủ công.

Token mới được mã hóa lại (access_token_enc) và cập nhật token_expires_at.
Đi qua proxy của account nếu có (giống các call outbound khác).
"""
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.crypto import decrypt_token, encrypt_token
from app.db.repository import TenantRepository
from app.services import proxy as proxy_service
from app.services.oauth import get_provider


async def refresh_account(
    db: AsyncIOMotorDatabase, user_id: str, account: dict
) -> dict:
    """Refresh token cho 1 account owned; trả về dict tóm tắt."""
    if account.get("type") != "owned" or not account.get("access_token_enc"):
        return {"status": "skipped", "error": "không phải owned / chưa có token"}

    provider = get_provider(account.get("platform", "threads"))
    refresh = getattr(provider, "refresh", None)
    if refresh is None:
        return {"status": "skipped", "error": "provider không hỗ trợ refresh"}

    token = decrypt_token(account["access_token_enc"])
    proxy = await proxy_service.resolve_for_account(db, user_id, account)
    tokens = await refresh(token, proxy=proxy)

    accounts = TenantRepository(db["accounts"], user_id)
    await accounts.update_one(
        {"_id": accounts.oid(account["_id"])},
        {
            "$set": {
                "access_token_enc": encrypt_token(tokens.access_token),
                "token_expires_at": tokens.expires_at,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    return {"status": "refreshed", "expires_at": tokens.expires_at}
