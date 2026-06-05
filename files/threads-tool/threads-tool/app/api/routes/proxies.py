"""
Quản lý proxy: CRUD + test kết nối. Mật khẩu lưu mã hóa (password_enc), không
bao giờ trả plaintext ra ngoài. Khi xóa proxy, mọi account đang gán nó sẽ được
gỡ liên kết (proxy_id -> None) để tránh trỏ tới proxy không còn tồn tại.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.crypto import encrypt_token
from app.core.deps import RepoFactory, get_repos
from app.models.proxy import ProxyCheck, ProxyCreate, ProxyPublic, ProxyUpdate
from app.services import proxy as proxy_service

router = APIRouter(prefix="/proxies", tags=["proxies"])


def _to_public(doc: dict) -> ProxyPublic:
    lc = doc.get("last_check")
    return ProxyPublic(
        id=str(doc["_id"]),
        label=doc["label"],
        protocol=doc.get("protocol", "http"),
        host=doc["host"],
        port=doc["port"],
        username=doc.get("username"),
        has_password=bool(doc.get("password_enc")),
        active=doc.get("active", True),
        last_check=ProxyCheck(**lc) if lc else None,
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


@router.get("", response_model=list[ProxyPublic])
async def list_proxies(repos: RepoFactory = Depends(get_repos)):
    docs = await repos("proxies").find_many(sort=[("_id", -1)])
    return [_to_public(d) for d in docs]


@router.post("", response_model=ProxyPublic, status_code=status.HTTP_201_CREATED)
async def create_proxy(payload: ProxyCreate, repos: RepoFactory = Depends(get_repos)):
    proxies = repos("proxies")
    now = datetime.now(timezone.utc)
    doc = {
        "label": payload.label,
        "protocol": payload.protocol,
        "host": payload.host,
        "port": payload.port,
        "username": payload.username,
        "password_enc": encrypt_token(payload.password) if payload.password else None,
        "active": payload.active,
        "last_check": None,
        "created_at": now,
        "updated_at": now,
    }
    new_id = await proxies.insert_one(doc)
    created = await proxies.find_one({"_id": proxies.oid(new_id)})
    return _to_public(created)


@router.patch("/{proxy_id}", response_model=ProxyPublic)
async def update_proxy(
    proxy_id: str, payload: ProxyUpdate, repos: RepoFactory = Depends(get_repos)
):
    proxies = repos("proxies")
    doc = await proxies.find_one({"_id": proxies.oid(proxy_id)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proxy không tồn tại")

    changes = payload.model_dump(exclude_unset=True)
    if "password" in changes:
        pw = changes.pop("password")
        changes["password_enc"] = encrypt_token(pw) if pw else None
    changes["updated_at"] = datetime.now(timezone.utc)
    await proxies.update_one({"_id": proxies.oid(proxy_id)}, {"$set": changes})

    updated = await proxies.find_one({"_id": proxies.oid(proxy_id)})
    return _to_public(updated)


@router.delete("/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proxy(proxy_id: str, repos: RepoFactory = Depends(get_repos)):
    proxies = repos("proxies")
    res = await proxies.delete_one({"_id": proxies.oid(proxy_id)})
    if res.deleted_count == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proxy không tồn tại")
    # Gỡ liên kết ở mọi account đang trỏ tới proxy này.
    await repos("accounts").update_many(
        {"proxy_id": proxy_id}, {"$set": {"proxy_id": None}}
    )
    return None


@router.post("/{proxy_id}/test", response_model=ProxyCheck)
async def test_proxy(proxy_id: str, repos: RepoFactory = Depends(get_repos)):
    proxies = repos("proxies")
    doc = await proxies.find_one({"_id": proxies.oid(proxy_id)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proxy không tồn tại")
    result = await proxy_service.test_proxy(doc)
    await proxies.update_one(
        {"_id": proxies.oid(proxy_id)}, {"$set": {"last_check": result}}
    )
    return ProxyCheck(**result)
