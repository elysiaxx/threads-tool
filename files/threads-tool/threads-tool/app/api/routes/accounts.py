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
from app.models.account import (
    AccountPublic,
    AssignProxyIn,
    ThreadsPublicPost,
    TrackAccountIn,
)
from app.services import proxy as proxy_service
from app.services.threads_public import ThreadsPublicClient, ThreadsPublicError
from app.services import token_refresh
from app.services.oauth import get_provider

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _to_public(doc: dict) -> AccountPublic:
    return AccountPublic(
        id=str(doc["_id"]),
        type=doc.get("type", "owned"),
        platform=doc.get("platform", "threads"),
        threads_user_id=doc.get("threads_user_id"),
        username=doc.get("username"),
        full_name=doc.get("full_name"),
        follower_count=doc.get("follower_count"),
        media_count=doc.get("media_count"),
        biography=doc.get("biography"),
        profile_pic_url=doc.get("profile_pic_url"),
        last_synced_at=doc.get("last_synced_at"),
        token_expires_at=doc.get("token_expires_at"),
        connected=bool(doc.get("access_token_enc")),
        proxy_id=doc.get("proxy_id"),
    )


def _provider_or_404(platform: str):
    try:
        return get_provider(platform)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Không có provider cho '{platform}'")


async def _threads_public_client(db: AsyncIOMotorDatabase, user_id: str) -> ThreadsPublicClient:
    proxy = await proxy_service.pick_from_pool(db, user_id)
    return ThreadsPublicClient(proxy=proxy)


def _public_profile_update(profile: dict, now: datetime) -> dict:
    return {
        "threads_user_id": profile.get("threads_user_id"),
        "username": profile.get("username"),
        "full_name": profile.get("full_name"),
        "follower_count": profile.get("follower_count"),
        "media_count": profile.get("media_count"),
        "biography": profile.get("biography"),
        "profile_pic_url": profile.get("profile_pic_url"),
        "last_synced_at": now,
        "updated_at": now,
    }


@router.get("", response_model=list[AccountPublic])
async def list_accounts(repos: RepoFactory = Depends(get_repos)):
    accounts = repos("accounts")
    docs = await accounts.find_many(sort=[("_id", -1)])
    return [_to_public(d) for d in docs]


@router.post("/track", response_model=AccountPublic, status_code=status.HTTP_201_CREATED)
async def track_account(
    payload: TrackAccountIn,
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    accounts = repos("accounts")
    username = payload.username.strip().lstrip("@")
    if not username:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "username không được rỗng")

    now = datetime.now(timezone.utc)
    public_fields: dict = {"username": username, "updated_at": now}
    if payload.platform == "threads":
        try:
            client = await _threads_public_client(db, repos.user_id)
            profile = await client.get_profile_by_username(username)
            public_fields.update(_public_profile_update(profile, now))
            username = public_fields["username"]
        except ThreadsPublicError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Không đọc được tài khoản Threads công khai: {exc}",
            ) from exc

    existing = await accounts.find_one(
        {"type": "tracked", "platform": payload.platform, "username": username}
    )
    if existing:
        await accounts.update_one(
            {"_id": existing["_id"]},
            {"$set": public_fields},
        )
        existing = await accounts.find_one({"_id": existing["_id"]})
        return _to_public(existing)

    new_id = await accounts.insert_one(
        {
            "type": "tracked",
            "platform": payload.platform,
            **public_fields,
            "created_at": now,
        }
    )
    doc = await accounts.find_one({"_id": accounts.oid(new_id)})
    return _to_public(doc)


@router.post("/{account_id}/sync-public", response_model=AccountPublic)
async def sync_public_account(
    account_id: str,
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    accounts = repos("accounts")
    acc = await accounts.find_one({"_id": accounts.oid(account_id)})
    if not acc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account không tồn tại")
    if acc.get("platform") != "threads":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chỉ hỗ trợ Threads")
    if not acc.get("username"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Account chưa có username")

    try:
        client = await _threads_public_client(db, repos.user_id)
        profile = await client.get_profile_by_username(acc["username"])
    except ThreadsPublicError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Không đồng bộ được profile Threads public: {exc}",
        ) from exc

    await accounts.update_one(
        {"_id": accounts.oid(account_id)},
        {"$set": _public_profile_update(profile, datetime.now(timezone.utc))},
    )
    updated = await accounts.find_one({"_id": accounts.oid(account_id)})
    return _to_public(updated)


@router.get("/{account_id}/public-posts", response_model=list[ThreadsPublicPost])
async def list_public_posts(
    account_id: str,
    kind: str = Query("threads", pattern="^(threads|replies)$"),
    limit: int = Query(25, ge=1, le=50),
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    accounts = repos("accounts")
    acc = await accounts.find_one({"_id": accounts.oid(account_id)})
    if not acc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account không tồn tại")
    if acc.get("platform") != "threads":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chỉ hỗ trợ Threads")

    username = acc.get("username")
    threads_user_id = acc.get("threads_user_id")
    try:
        client = await _threads_public_client(db, repos.user_id)
        if not threads_user_id:
            if not username:
                raise ThreadsPublicError("account chưa có username hoặc threads_user_id")
            profile = await client.get_profile_by_username(username)
            threads_user_id = profile["threads_user_id"]
            await accounts.update_one(
                {"_id": accounts.oid(account_id)},
                {"$set": _public_profile_update(profile, datetime.now(timezone.utc))},
            )
        return await client.list_user_posts(
            threads_user_id,
            username=username,
            kind=kind,  # type: ignore[arg-type]
            limit=limit,
        )
    except ThreadsPublicError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Không đọc được bài viết public: {exc}",
        ) from exc


@router.post("/{account_id}/refresh-token", response_model=AccountPublic)
async def refresh_token(
    account_id: str,
    repos: RepoFactory = Depends(get_repos),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Gia hạn token Threads của account ngay lập tức (chạy đồng bộ để trả kết quả)."""
    accounts = repos("accounts")
    acc = await accounts.find_one({"_id": accounts.oid(account_id)})
    if not acc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account không tồn tại")
    result = await token_refresh.refresh_account(db, repos.user_id, acc)
    if result.get("status") not in ("refreshed",):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, result.get("error") or "Không refresh được"
        )
    updated = await accounts.find_one({"_id": accounts.oid(account_id)})
    return _to_public(updated)


@router.patch("/{account_id}/proxy", response_model=AccountPublic)
async def assign_proxy(
    account_id: str, payload: AssignProxyIn, repos: RepoFactory = Depends(get_repos)
):
    """Gán/gỡ proxy cố định cho account. proxy_id=null -> fallback về pool."""
    accounts = repos("accounts")
    acc = await accounts.find_one({"_id": accounts.oid(account_id)})
    if not acc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account không tồn tại")
    if payload.proxy_id:
        proxies = repos("proxies")
        if not await proxies.find_one({"_id": proxies.oid(payload.proxy_id)}):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Proxy không tồn tại")
    await accounts.update_one(
        {"_id": accounts.oid(account_id)},
        {"$set": {"proxy_id": payload.proxy_id, "updated_at": datetime.now(timezone.utc)}},
    )
    updated = await accounts.find_one({"_id": accounts.oid(account_id)})
    return _to_public(updated)


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
    code: str | None = Query(None),
    state: str | None = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    if not code or not state:
        return {"status": "ok", "platform": platform}

    user_id = verify_state_token(state)
    if not user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OAuth state không hợp lệ/hết hạn")

    provider = _provider_or_404(platform)
    proxy = await proxy_service.pick_from_pool(db, user_id)
    tokens = await provider.exchange_code(code, proxy=proxy)

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


@router.api_route("/oauth/{platform}/deauthorize", methods=["GET", "POST"])
async def oauth_deauthorize(platform: str):
    """Endpoint callback để Meta gọi khi user gỡ quyền app."""
    return {"status": "ok", "platform": platform}


@router.api_route("/oauth/{platform}/delete", methods=["GET", "POST"])
async def oauth_data_delete(platform: str):
    """Endpoint callback tối thiểu cho yêu cầu xóa dữ liệu từ Meta."""
    return {
        "url": settings.frontend_url,
        "confirmation_code": f"{platform}-data-deletion-received",
    }
