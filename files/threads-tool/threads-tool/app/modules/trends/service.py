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
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.db.repository import TenantRepository
from app.models.trend_radar import (
    RadarBucket,
    RadarPost,
    RadarSettings,
    RadarStats,
)
from app.services import proxy as proxy_service
from app.services.threads_public import ThreadsPublicClient, ThreadsPublicError

# Threads dùng media_type dạng số; map sang nhãn hiển thị.
_MEDIA_TYPE_LABELS = {0: "TEXT", 1: "IMAGE", 2: "VIDEO", 8: "CAROUSEL", 19: "TEXT"}
_POSTS_PER_ACCOUNT = 25


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


# --- Thu thập (gọi từ Celery) ------------------------------------------------
async def _upsert_public_post(repo: TenantRepository, acc: dict, p: dict, now: datetime) -> bool:
    post_id = p.get("id")
    if not post_id:
        return False

    existing = await repo.find_one({"post_id": post_id})
    like = p.get("like_count") or 0
    reply = p.get("reply_count") or 0
    quote = p.get("quote_count") or 0
    fields = {
        "post_id": str(post_id),
        "account_id": str(acc["_id"]),
        "username": acc.get("username"),
        "code": p.get("code"),
        "permalink": p.get("permalink"),
        "text": p.get("text"),
        "taken_at": _parse_ts(p.get("taken_at")),
        "media_type_raw": p.get("media_type"),
        "image_url": p.get("image_url"),
        "video_url": p.get("video_url"),
        "author": p.get("user") or {},
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


async def collect_tracked(user_id: str) -> dict:
    """Đọc public posts của mọi tracked account -> snapshot public_posts."""
    client = AsyncIOMotorClient(settings.mongo_uri)
    try:
        db = client[settings.mongo_db]
        accounts = TenantRepository(db["accounts"], user_id)
        tracked = await accounts.find_many({"type": "tracked", "platform": "threads"})
        if not tracked:
            return {"status": "skipped", "error": "chưa có tracked account"}

        proxy = await proxy_service.pick_from_pool(db, user_id)
        reader = ThreadsPublicClient(proxy=proxy)
        public_posts = TenantRepository(db["public_posts"], user_id)
        now = datetime.now(timezone.utc)

        collected = 0
        errors: list[str] = []
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
                # Lỗi logic/parse của 1 account: ghi nhận, không chặn cả batch.
                errors.append(f"@{username}: {exc}")
                continue
            # Lỗi mạng/5xx/429 cố ý KHÔNG bắt ở đây: để bubble lên _run -> Celery
            # retry toàn task (raise_if_transient).

            for p in posts:
                if await _upsert_public_post(public_posts, acc, p, now):
                    collected += 1

        return {
            "status": "ok",
            "accounts": len(tracked),
            "collected": collected,
            "errors": errors,
        }
    finally:
        client.close()
