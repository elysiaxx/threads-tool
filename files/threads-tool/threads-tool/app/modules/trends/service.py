"""
Trend Radar — thu thập nội dung public của watchlist & chấm điểm xu hướng.

- collect_tracked: với mỗi tracked account của user, đọc public posts qua
  ThreadsPublicClient (KHÔNG cần OAuth) rồi snapshot vào `public_posts`. Mỗi lần
  thu thập lưu cả mốc trước để tính velocity (tốc độ tăng tương tác/giờ).
- list_trending / compute_stats: chấm điểm LÚC ĐỌC theo RadarSettings, nên đổi
  ngưỡng là bảng xếp hạng đổi ngay (không cần thu thập lại).

Score = engagement / (age_hours + 2) ^ gravity   (decay theo độ mới, kiểu HN).
engagement = like + reply_weight·reply + quote_weight·quote.

Mọi truy cập `public_posts` / `trend_settings` đều qua TenantRepository để giữ
cách ly tenant. Hàm collect tự mở motor client riêng (gọi từ Celery sync).
"""
import json
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.db.repository import TenantRepository
from app.core.crypto import decrypt_token, encrypt_token
from app.models.trend_radar import (
    RadarBucket,
    RadarPost,
    RadarSession,
    RadarSettings,
    RadarStats,
    RadarStatus,
    RadarWatchItem,
    TargetCreate,
    TrackTarget,
)
from app.services import proxy as proxy_service
from app.services.threads_public import (
    ThreadsPublicClient,
    ThreadsPublicError,
    extract_shortcode,
)

# Threads dùng media_type dạng số; map sang nhãn hiển thị.
_MEDIA_TYPE_LABELS = {0: "TEXT", 1: "IMAGE", 2: "VIDEO", 8: "CAROUSEL", 19: "TEXT"}
_POSTS_PER_ACCOUNT = 25
_POSTS_PER_TARGET = 25
_COOKIE_PRIORITY = ("sessionid", "csrftoken", "ds_user_id")


def _public_client(
    proxy: Optional[str],
    cookie: Optional[str] = None,
    *,
    search_doc_id: Optional[str] = None,
    search_friendly_name: Optional[str] = None,
) -> ThreadsPublicClient:
    """ThreadsPublicClient có cookie (đăng nhập) + cấu hình search doc_id từ env."""
    return ThreadsPublicClient(
        proxy=proxy,
        cookie=cookie,
        search_doc_id=search_doc_id or settings.threads_search_doc_id or None,
        search_friendly_name=search_friendly_name or settings.threads_search_friendly_name,
    )


# --- Session cookie (đăng nhập public để search) -----------------------------
async def _session_doc(db: AsyncIOMotorDatabase, user_id: str) -> dict:
    repo = TenantRepository(db["radar_session"], user_id)
    return await repo.find_one({}) or {}


async def _session_cookie(db: AsyncIOMotorDatabase, user_id: str) -> Optional[str]:
    """Cookie phiên Threads đã giải mã (None nếu chưa cấu hình)."""
    doc = await _session_doc(db, user_id)
    enc = (doc or {}).get("cookie_enc")
    if not enc:
        return None
    try:
        return decrypt_token(enc)
    except Exception:  # noqa: BLE001 - key đổi/hỏng -> coi như chưa có
        return None


async def _session_search_config(db: AsyncIOMotorDatabase, user_id: str) -> dict:
    doc = await _session_doc(db, user_id)
    return {
        "search_doc_id": doc.get("search_doc_id") or None,
        "search_friendly_name": doc.get("search_friendly_name") or None,
    }


async def get_session(db: AsyncIOMotorDatabase, user_id: str) -> RadarSession:
    doc = await _session_doc(db, user_id)
    return RadarSession(
        has_cookie=bool(doc.get("cookie_enc")),
        updated_at=doc.get("updated_at"),
        last_check_ok=(doc.get("last_check") or {}).get("ok"),
        last_check_at=(doc.get("last_check") or {}).get("checked_at"),
        last_check_error=(doc.get("last_check") or {}).get("error"),
        search_doc_id=doc.get("search_doc_id"),
        search_friendly_name=doc.get("search_friendly_name"),
        doc_id_updated_at=doc.get("doc_id_updated_at"),
    )


def _cookie_pairs_from_header(cookie: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name and value:
            pairs.append((name, value))
    return pairs


def _cookie_header_from_export(items: list) -> str:
    pairs_by_name: dict[str, str] = {}
    order: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        if not name or not value:
            continue
        if name not in pairs_by_name:
            order.append(name)
        pairs_by_name[name] = value

    if "sessionid" not in pairs_by_name:
        raise ValueError("Thiếu sessionid")

    ordered_names = [name for name in _COOKIE_PRIORITY if name in pairs_by_name]
    ordered_names.extend(name for name in order if name not in ordered_names)
    return "; ".join(f"{name}={pairs_by_name[name]}" for name in ordered_names)


def normalize_session_cookie(cookie: str) -> str:
    cookie = (cookie or "").strip()
    if not cookie:
        raise ValueError("Cookie không được rỗng")

    if cookie[0] in "[{":
        try:
            parsed = json.loads(cookie)
        except json.JSONDecodeError as exc:
            raise ValueError("File cookie không hợp lệ") from exc
        if not isinstance(parsed, list):
            raise ValueError("File cookie không hợp lệ")
        return _cookie_header_from_export(parsed)

    pairs = _cookie_pairs_from_header(cookie)
    if not any(name == "sessionid" for name, _ in pairs):
        raise ValueError("Thiếu sessionid")
    return "; ".join(f"{name}={value}" for name, value in pairs)


async def save_session(db: AsyncIOMotorDatabase, user_id: str, cookie: str) -> RadarSession:
    cookie = normalize_session_cookie(cookie)
    if not cookie:
        raise ValueError("Cookie không được rỗng")
    repo = TenantRepository(db["radar_session"], user_id)
    await repo.update_one(
        {},
        {"$set": {"cookie_enc": encrypt_token(cookie), "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return await get_session(db, user_id)


async def import_browser_session(
    db: AsyncIOMotorDatabase,
    user_id: str,
    *,
    cookie: str,
    search_doc_id: Optional[str] = None,
    search_friendly_name: Optional[str] = None,
) -> RadarSession:
    cookie = normalize_session_cookie(cookie)
    now = datetime.now(timezone.utc)
    fields = {"cookie_enc": encrypt_token(cookie), "updated_at": now}
    if search_doc_id:
        fields["search_doc_id"] = str(search_doc_id).strip()
        fields["search_friendly_name"] = (
            str(search_friendly_name).strip()
            if search_friendly_name
            else settings.threads_search_friendly_name
        )
        fields["doc_id_updated_at"] = now
    repo = TenantRepository(db["radar_session"], user_id)
    await repo.update_one({}, {"$set": fields}, upsert=True)
    return await get_session(db, user_id)


async def clear_session(db: AsyncIOMotorDatabase, user_id: str) -> None:
    repo = TenantRepository(db["radar_session"], user_id)
    await repo.delete_one({})


async def test_session(db: AsyncIOMotorDatabase, user_id: str) -> dict:
    """Thử 1 search nhỏ để kiểm tra cookie còn hiệu lực. Ghi lại last_check."""
    cookie = await _session_cookie(db, user_id)
    if not cookie:
        return {"ok": False, "error": "Chưa có cookie"}
    proxy = await proxy_service.pick_from_pool(db, user_id)
    search_config = await _session_search_config(db, user_id)
    reader = _public_client(proxy, cookie, **search_config)
    now = datetime.now(timezone.utc)
    try:
        posts = await reader.search_posts("threads", limit=3)
        result = {"ok": True, "count": len(posts), "error": None, "checked_at": now}
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "count": 0, "error": str(exc), "checked_at": now}
    repo = TenantRepository(db["radar_session"], user_id)
    await repo.update_one({}, {"$set": {"last_check": result}}, upsert=True)
    return result


async def discover_session_doc_id(db: AsyncIOMotorDatabase, user_id: str) -> dict:
    """Dò GraphQL doc_id search bằng cookie đã lưu và ghi metadata vào radar_session."""
    cookie = await _session_cookie(db, user_id)
    if not cookie:
        return {"ok": False, "error": "Chưa có cookie"}

    proxy = await proxy_service.pick_from_pool(db, user_id)
    search_config = await _session_search_config(db, user_id)
    reader = _public_client(proxy, cookie, **search_config)
    now = datetime.now(timezone.utc)
    repo = TenantRepository(db["radar_session"], user_id)
    try:
        found = await reader.discover_search_doc_id("threads")
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": str(exc), "checked_at": now}
        await repo.update_one({}, {"$set": {"last_doc_id_check": result}}, upsert=True)
        return result

    if not found:
        result = {
            "ok": False,
            "error": "Không tìm thấy search doc_id trong trang Threads",
            "checked_at": now,
        }
        await repo.update_one({}, {"$set": {"last_doc_id_check": result}}, upsert=True)
        return result

    result = {
        "ok": True,
        "doc_id": found["doc_id"],
        "friendly_name": found["friendly_name"],
        "checked_at": now,
    }
    await repo.update_one(
        {},
        {
            "$set": {
                "search_doc_id": found["doc_id"],
                "search_friendly_name": found["friendly_name"],
                "doc_id_updated_at": now,
                "last_doc_id_check": result,
            }
        },
        upsert=True,
    )
    return result


def _media_label(raw) -> str:
    return _MEDIA_TYPE_LABELS.get(raw, "OTHER") if raw is not None else "TEXT"


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("+0000", "+00:00"))
    except ValueError:
        return None


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# --- Settings ----------------------------------------------------------------
async def get_settings(db: AsyncIOMotorDatabase, user_id: str) -> RadarSettings:
    repo = TenantRepository(db["trend_settings"], user_id)
    doc = await repo.find_one({})
    if not doc:
        return RadarSettings()
    doc.pop("_id", None)
    doc.pop("user_id", None)
    return RadarSettings(**{k: v for k, v in doc.items() if k in RadarSettings.model_fields})


async def save_settings(
    db: AsyncIOMotorDatabase, user_id: str, new: RadarSettings
) -> RadarSettings:
    repo = TenantRepository(db["trend_settings"], user_id)
    await repo.update_one(
        {},
        {"$set": {**new.model_dump(), "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return new


# --- Scoring -----------------------------------------------------------------
def _engagement(like: float, reply: float, quote: float, s: RadarSettings) -> float:
    return like + s.reply_weight * reply + s.quote_weight * quote


def _score(engagement: float, age_hours: float, s: RadarSettings) -> float:
    return engagement / pow(max(age_hours, 0) + 2, s.gravity)


def _scored_post(doc: dict, s: RadarSettings, now: datetime) -> RadarPost:
    like = doc.get("like_count") or 0
    reply = doc.get("reply_count") or 0
    quote = doc.get("quote_count") or 0
    engagement = _engagement(like, reply, quote, s)

    taken_at = _as_utc(doc.get("taken_at"))
    age_hours = (now - taken_at).total_seconds() / 3600 if taken_at else 0.0
    score = _score(engagement, age_hours, s)

    # Velocity từ snapshot trước (cùng trọng số hiện tại).
    velocity = None
    prev_at = _as_utc(doc.get("prev_collected_at"))
    collected_at = _as_utc(doc.get("collected_at"))
    if prev_at and collected_at:
        dt_hours = (collected_at - prev_at).total_seconds() / 3600
        if dt_hours > 0:
            prev_eng = _engagement(
                doc.get("prev_like_count") or 0,
                doc.get("prev_reply_count") or 0,
                doc.get("prev_quote_count") or 0,
                s,
            )
            velocity = round((engagement - prev_eng) / dt_hours, 2)

    author = doc.get("author") or {}
    return RadarPost(
        id=str(doc.get("post_id") or doc.get("_id")),
        account_id=doc.get("account_id"),
        source_kind=doc.get("source_kind"),
        source_value=doc.get("source_value"),
        permalink=doc.get("permalink"),
        text=doc.get("text"),
        taken_at=taken_at,
        media_type=_media_label(doc.get("media_type_raw")),
        image_url=doc.get("image_url"),
        like_count=like,
        reply_count=reply,
        quote_count=quote,
        engagement=round(engagement, 2),
        score=round(score, 4),
        velocity=velocity,
        age_hours=round(age_hours, 1),
        collected_at=collected_at,
        author={
            "id": author.get("id"),
            "username": author.get("username") or doc.get("username"),
            "full_name": author.get("full_name"),
            "profile_pic_url": author.get("profile_pic_url"),
            "is_verified": author.get("is_verified"),
        },
    )


def _passes(p: RadarPost, s: RadarSettings) -> bool:
    return (
        p.like_count >= s.min_likes
        and p.engagement >= s.min_engagement
        and (p.age_hours is None or p.age_hours <= s.max_age_hours)
        and p.score >= s.min_score
    )


async def _load_scored(
    db: AsyncIOMotorDatabase, user_id: str, s: RadarSettings
) -> list[RadarPost]:
    repo = TenantRepository(db["public_posts"], user_id)
    docs = await repo.find_many(sort=[("collected_at", -1)], limit=2000)
    now = datetime.now(timezone.utc)
    return [_scored_post(d, s, now) for d in docs]


# --- Đọc cho API -------------------------------------------------------------
async def list_trending(
    db: AsyncIOMotorDatabase,
    user_id: str,
    overrides: Optional[dict] = None,
) -> list[RadarPost]:
    s = await get_settings(db, user_id)
    if overrides:
        s = s.model_copy(update={k: v for k, v in overrides.items() if v is not None})
    scored = [p for p in await _load_scored(db, user_id, s) if _passes(p, s)]
    scored.sort(key=lambda p: p.score, reverse=True)
    return scored[: s.top_n]


async def compute_stats(db: AsyncIOMotorDatabase, user_id: str) -> RadarStats:
    s = await get_settings(db, user_id)
    allp = await _load_scored(db, user_id, s)
    trending = [p for p in allp if _passes(p, s)]

    by_account: dict[str, RadarBucket] = {}
    by_media: dict[str, RadarBucket] = {}
    by_day: dict[str, RadarBucket] = {}
    for p in trending:
        uname = (p.author.username if p.author else None) or "?"
        ba = by_account.setdefault(uname, RadarBucket(label=uname))
        ba.count += 1
        ba.engagement += p.engagement

        mt = p.media_type or "OTHER"
        bm = by_media.setdefault(mt, RadarBucket(label=mt))
        bm.count += 1
        bm.engagement += p.engagement

        if p.taken_at:
            day = p.taken_at.date().isoformat()
            bd = by_day.setdefault(day, RadarBucket(label=day))
            bd.count += 1
            bd.engagement += p.engagement

    last_collected = max((p.collected_at for p in allp if p.collected_at), default=None)
    total_eng = sum(p.engagement for p in trending)
    return RadarStats(
        tracked_posts=len(allp),
        trending_posts=len(trending),
        source_accounts=len({p.account_id for p in allp if p.account_id}),
        avg_engagement=round(total_eng / len(trending), 1) if trending else 0,
        by_account=sorted(by_account.values(), key=lambda b: b.engagement, reverse=True)[:10],
        by_media_type=sorted(by_media.values(), key=lambda b: b.count, reverse=True),
        timeline=sorted(by_day.values(), key=lambda b: b.label),
        last_collected_at=last_collected,
    )


async def list_watchlist(db: AsyncIOMotorDatabase, user_id: str) -> list[RadarWatchItem]:
    """Watchlist (tracked accounts) + số bài đã thu thập / trending của từng tài khoản."""
    s = await get_settings(db, user_id)
    accounts = TenantRepository(db["accounts"], user_id)
    tracked = await accounts.find_many(
        {"type": "tracked", "platform": "threads"}, sort=[("username", 1)]
    )

    agg: dict[str, dict] = {}
    for p in await _load_scored(db, user_id, s):
        b = agg.setdefault(p.account_id, {"collected": 0, "trending": 0, "last": None})
        b["collected"] += 1
        if _passes(p, s):
            b["trending"] += 1
        if p.collected_at and (b["last"] is None or p.collected_at > b["last"]):
            b["last"] = p.collected_at

    items: list[RadarWatchItem] = []
    for a in tracked:
        aid = str(a["_id"])
        b = agg.get(aid, {"collected": 0, "trending": 0, "last": None})
        items.append(
            RadarWatchItem(
                account_id=aid,
                username=a.get("username"),
                full_name=a.get("full_name"),
                profile_pic_url=a.get("profile_pic_url"),
                follower_count=a.get("follower_count"),
                collected_posts=b["collected"],
                trending_posts=b["trending"],
                last_collected_at=b["last"],
            )
        )
    return items


async def get_status(db: AsyncIOMotorDatabase, user_id: str) -> RadarStatus:
    repo = TenantRepository(db["radar_status"], user_id)
    doc = await repo.find_one({})
    if not doc:
        return RadarStatus()
    return RadarStatus(
        state=doc.get("state", "idle"),
        started_at=doc.get("started_at"),
        finished_at=doc.get("finished_at"),
        accounts=doc.get("accounts", 0),
        collected=doc.get("collected", 0),
        errors=doc.get("errors", []),
    )


# --- Targets (keyword/hashtag/link) ------------------------------------------
def _normalize_target_value(kind: str, value: str) -> str:
    value = (value or "").strip()
    if kind == "hashtag":
        value = "#" + value.lstrip("#")
    return value


async def list_targets(db: AsyncIOMotorDatabase, user_id: str) -> list[TrackTarget]:
    """Các nguồn keyword/hashtag/link + số bài thu thập/trending mỗi nguồn."""
    s = await get_settings(db, user_id)
    repo = TenantRepository(db["watch_targets"], user_id)
    targets = await repo.find_many(sort=[("created_at", -1)])

    agg: dict[tuple, dict] = {}
    for p in await _load_scored(db, user_id, s):
        if not p.source_kind or p.source_kind == "account":
            continue
        key = (p.source_kind, p.source_value)
        b = agg.setdefault(key, {"collected": 0, "trending": 0, "last": None})
        b["collected"] += 1
        if _passes(p, s):
            b["trending"] += 1
        if p.collected_at and (b["last"] is None or p.collected_at > b["last"]):
            b["last"] = p.collected_at

    items: list[TrackTarget] = []
    for t in targets:
        b = agg.get((t.get("kind"), t.get("value")), {"collected": 0, "trending": 0, "last": None})
        items.append(
            TrackTarget(
                id=str(t["_id"]),
                kind=t.get("kind"),
                value=t.get("value"),
                collected_posts=b["collected"],
                trending_posts=b["trending"],
                last_collected_at=b["last"],
                created_at=t.get("created_at"),
            )
        )
    return items


async def add_target(db: AsyncIOMotorDatabase, user_id: str, payload: TargetCreate) -> TrackTarget:
    repo = TenantRepository(db["watch_targets"], user_id)
    value = _normalize_target_value(payload.kind, payload.value)
    if not value or value in ("#",):
        raise ValueError("Giá trị theo dõi không được rỗng")
    now = datetime.now(timezone.utc)
    existing = await repo.find_one({"kind": payload.kind, "value": value})
    if existing:
        return TrackTarget(
            id=str(existing["_id"]), kind=existing["kind"], value=existing["value"],
            created_at=existing.get("created_at"),
        )
    new_id = await repo.insert_one({"kind": payload.kind, "value": value, "created_at": now})
    return TrackTarget(id=str(new_id), kind=payload.kind, value=value, created_at=now)


async def remove_target(db: AsyncIOMotorDatabase, user_id: str, target_id: str) -> bool:
    repo = TenantRepository(db["watch_targets"], user_id)
    res = await repo.delete_one({"_id": repo.oid(target_id)})
    return res.deleted_count > 0


# --- Thu thập (gọi từ Celery) ------------------------------------------------
async def _upsert_public_post(
    repo: TenantRepository,
    p: dict,
    now: datetime,
    *,
    account_id: Optional[str],
    source_kind: str,
    source_value: Optional[str],
) -> bool:
    post_id = p.get("id")
    if not post_id:
        return False

    existing = await repo.find_one({"post_id": post_id})
    like = p.get("like_count") or 0
    reply = p.get("reply_count") or 0
    quote = p.get("quote_count") or 0
    author = p.get("user") or {}
    fields = {
        "post_id": str(post_id),
        "account_id": account_id,
        "source_kind": source_kind,
        "source_value": source_value,
        "username": (author.get("username") if author else None),
        "code": p.get("code"),
        "permalink": p.get("permalink"),
        "text": p.get("text"),
        "taken_at": _parse_ts(p.get("taken_at")),
        "media_type_raw": p.get("media_type"),
        "image_url": p.get("image_url"),
        "video_url": p.get("video_url"),
        "author": author,
        "like_count": like,
        "reply_count": reply,
        "quote_count": quote,
        "collected_at": now,
        "updated_at": now,
    }
    if existing:
        fields.update(
            {
                "prev_like_count": existing.get("like_count", 0),
                "prev_reply_count": existing.get("reply_count", 0),
                "prev_quote_count": existing.get("quote_count", 0),
                "prev_collected_at": existing.get("collected_at"),
                "first_seen_at": existing.get("first_seen_at", now),
            }
        )
        await repo.update_one({"_id": existing["_id"]}, {"$set": fields})
    else:
        fields["first_seen_at"] = now
        await repo.insert_one(fields)
    return True


async def _target_posts(reader: ThreadsPublicClient, kind: str, value: str) -> list[dict]:
    """Lấy post cho 1 target theo loại (keyword/hashtag/link)."""
    if kind == "hashtag":
        return await reader.search_posts("#" + value.lstrip("#"), limit=_POSTS_PER_TARGET)
    if kind == "keyword":
        return await reader.search_posts(value, limit=_POSTS_PER_TARGET)
    if kind == "link":
        # URL/shortcode 1 bài Threads -> track đúng bài đó; còn lại coi như keyword.
        if extract_shortcode(value):
            return [await reader.get_post(value)]
        return await reader.search_posts(value, limit=_POSTS_PER_TARGET)
    return []


async def _do_collect(db: AsyncIOMotorDatabase, user_id: str) -> dict:
    accounts = TenantRepository(db["accounts"], user_id)
    targets_repo = TenantRepository(db["watch_targets"], user_id)
    tracked = await accounts.find_many({"type": "tracked", "platform": "threads"})
    targets = await targets_repo.find_many()
    if not tracked and not targets:
        return {
            "status": "skipped",
            "error": "chưa có nguồn theo dõi (account/keyword/hashtag/link)",
            "accounts": 0,
            "collected": 0,
            "errors": [],
        }

    proxy = await proxy_service.pick_from_pool(db, user_id)
    cookie = await _session_cookie(db, user_id)
    search_config = await _session_search_config(db, user_id)
    reader = _public_client(proxy, cookie, **search_config)
    public_posts = TenantRepository(db["public_posts"], user_id)
    now = datetime.now(timezone.utc)

    collected = 0
    errors: list[str] = []

    # 1) Tracked accounts -> bài của từng tài khoản.
    for acc in tracked:
        username = acc.get("username")
        threads_user_id = acc.get("threads_user_id")
        try:
            if not threads_user_id:
                if not username:
                    continue
                profile = await reader.get_profile_by_username(username)
                threads_user_id = profile["threads_user_id"]
                await accounts.update_one(
                    {"_id": acc["_id"]},
                    {"$set": {"threads_user_id": threads_user_id, "updated_at": now}},
                )
            posts = await reader.list_user_posts(
                threads_user_id, username=username, limit=_POSTS_PER_ACCOUNT
            )
        except ThreadsPublicError as exc:
            errors.append(f"@{username}: {exc}")
            continue
        # Lỗi mạng/5xx/429 cố ý KHÔNG bắt ở đây: bubble lên _run -> Celery retry.
        for p in posts:
            if await _upsert_public_post(
                public_posts, p, now,
                account_id=str(acc["_id"]), source_kind="account", source_value=username,
            ):
                collected += 1

    # 2) Targets keyword/hashtag/link -> kết quả search.
    for t in targets:
        kind = t.get("kind")
        value = (t.get("value") or "").strip()
        if not value or kind not in ("keyword", "hashtag", "link"):
            continue
        try:
            posts = await _target_posts(reader, kind, value)
        except ThreadsPublicError as exc:
            errors.append(f"{kind}:{value}: {exc}")
            continue
        for p in posts:
            if await _upsert_public_post(
                public_posts, p, now,
                account_id=None, source_kind=kind, source_value=value,
            ):
                collected += 1

    return {
        "status": "ok",
        "accounts": len(tracked),
        "targets": len(targets),
        "collected": collected,
        "errors": errors,
    }


async def collect_tracked(user_id: str) -> dict:
    """Thu thập public posts của watchlist + ghi trạng thái tiến trình (radar_status)."""
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        db = client[settings.mongo_db]
        status = TenantRepository(db["radar_status"], user_id)
        await status.update_one(
            {},
            {
                "$set": {
                    "state": "running",
                    "started_at": datetime.now(timezone.utc),
                    "finished_at": None,
                    "accounts": 0,
                    "collected": 0,
                    "errors": [],
                }
            },
            upsert=True,
        )
        try:
            result = await _do_collect(db, user_id)
        except Exception as exc:  # noqa: BLE001 - đánh dấu idle + lỗi rồi re-raise cho Celery
            await status.update_one(
                {},
                {"$set": {"state": "idle", "finished_at": datetime.now(timezone.utc), "errors": [str(exc)]}},
            )
            raise
        await status.update_one(
            {},
            {
                "$set": {
                    "state": "idle",
                    "finished_at": datetime.now(timezone.utc),
                    "accounts": result.get("accounts", 0),
                    "collected": result.get("collected", 0),
                    "errors": result.get("errors", []),
                }
            },
        )
        return result
    finally:
        client.close()
