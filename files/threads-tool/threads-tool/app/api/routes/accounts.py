"""
Quản lý tài khoản:
- owned: tài khoản Threads của user, kết nối qua OAuth (start -> callback).
- tracked: tài khoản/đối thủ chỉ theo dõi (chỉ cần username, không cần token).

Callback OAuth không có JWT (Meta redirect về), nên user_id được mang qua
"state" đã ký và verify lại trước khi lưu token (đã mã hóa) đúng chủ.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.core.crypto import encrypt_token
from app.core.deps import CurrentUser, RepoFactory, get_current_user, get_repos
from app.core.security import create_state_token, verify_state_token
from app.db.mongo import get_database
from app.db.repository import TenantRepository
from app.models.account import AccountPublic, TrackAccountIn
from app.services.oauth import get_provider

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _to_public(doc: dict) -> AccountPublic:
    return AccountPublic(
        id=str(doc["_id"]),
        type=doc.get("type", "owned"),
        platform=doc.get("platform", "threads"),
        threads_user_id=doc.get("threads_user_id"),
        username=doc.get("username"),
        token_expires_at=doc.get("token_expires_at"),
        connected=bool(doc.get("access_token_enc")),
    )


def _provider_or_404(platform: str):
    try:
        return get_provider(platform)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Không có provider cho '{platform}'")


@router.get("", response_model=list[AccountPublic])
async def list_accounts(repos: RepoFactory = Depends(get_repos)):
    accounts = repos("accounts")
    docs = await accounts.find_many(sort=[("_id", -1)])
    return [_to_public(d) for d in docs]


@router.post("/track", response_model=AccountPublic, status_code=status.HTTP_201_CREATED)
async def track_account(
    payload: TrackAccountIn, repos: RepoFactory = Depends(get_repos)
):
    accounts = repos("accounts")
    existing = await accounts.find_one(
        {"type": "tracked", "platform": payload.platform, "username": payload.username}
    )
    if existing:
        return _to_public(existing)
    new_id = await accounts.insert_one(
        {
            "type": "tracked",
            "platform": payload.platform,
            "username": payload.username,
            "created_at": datetime.now(timezone.utc),
        }
    )
    doc = await accounts.find_one({"_id": accounts.oid(new_id)})
    return _to_public(doc)


@router.get("/oauth/{platform}/authorize-url")
async def oauth_authorize_url(
    platform: str, user: CurrentUser = Depends(get_current_user)
):
    """Trả authorize URL dạng JSON để frontend (gửi kèm Bearer) tự điều hướng."""
    provider = _provider_or_404(platform)
    state = create_state_token(user.user_id)
    return {"url": provider.authorize_url(state)}


@router.get("/oauth/{platform}/start")
async def oauth_start(platform: str, user: CurrentUser = Depends(get_current_user)):
    provider = _provider_or_404(platform)
    state = create_state_token(user.user_id)
    return RedirectResponse(provider.authorize_url(state))


@router.get("/oauth/{platform}/callback")
async def oauth_callback(
    platform: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    user_id = verify_state_token(state)
    if not user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OAuth state không hợp lệ/hết hạn")

    provider = _provider_or_404(platform)
    tokens = await provider.exchange_code(code)

    # Lưu token đã MÃ HÓA, scoped theo user qua TenantRepository.
    repo = TenantRepository(db["accounts"], user_id)
    await repo.update_one(
        {"platform": platform, "type": "owned", "threads_user_id": tokens.external_user_id},
        {
            "$set": {
                "platform": platform,
                "type": "owned",
                "threads_user_id": tokens.external_user_id,
                "username": tokens.username,
                "access_token_enc": encrypt_token(tokens.access_token),
                "token_expires_at": tokens.expires_at,
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
    return RedirectResponse(f"{settings.frontend_url}/accounts?connected={platform}")
