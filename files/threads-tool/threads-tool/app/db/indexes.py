"""
Tạo index. Nguyên tắc: mọi compound index của collection thuộc user đều
BẮT ĐẦU bằng user_id (vừa khớp pattern truy vấn của TenantRepository, vừa nhanh).
metrics_ts là time-series collection với user_id/post_id nằm trong metaField.
"""
from app.db.mongo import get_database


async def ensure_indexes() -> None:
    db = get_database()

    await db.users.create_index("email", unique=True)

    await db.accounts.create_index(
        [("user_id", 1), ("platform", 1), ("threads_user_id", 1)],
        unique=True,
        sparse=True,
    )
    await db.accounts.create_index([("user_id", 1), ("type", 1)])

    await db.sources.create_index([("user_id", 1), ("status", 1)])

    await db.proxies.create_index([("user_id", 1), ("active", 1)])

    await db.jobs.create_index([("user_id", 1), ("status", 1), ("scheduled_at", 1)])

    await db.posts.create_index([("user_id", 1), ("published_at", -1)])
    await db.posts.create_index([("user_id", 1), ("account_id", 1)])

    await db.searches.create_index([("user_id", 1)])

    await db.trends.create_index([("user_id", 1), ("keyword", 1), ("ts", -1)])

    # Trend Radar: snapshot public posts theo (user_id, post_id) là duy nhất;
    # đọc theo collected_at để chấm điểm. trend_settings: 1 bản / user.
    await db.public_posts.create_index(
        [("user_id", 1), ("post_id", 1)], unique=True
    )
    await db.public_posts.create_index([("user_id", 1), ("collected_at", -1)])
    await db.trend_settings.create_index("user_id", unique=True)


async def ensure_timeseries() -> None:
    """metrics_ts: time-series collection. user_id + post_id để trong metaField."""
    db = get_database()
    names = await db.list_collection_names()
    if "metrics_ts" not in names:
        await db.create_collection(
            "metrics_ts",
            timeseries={
                "timeField": "ts",
                "metaField": "meta",  # { user_id, post_id }
                "granularity": "minutes",
            },
        )
    await db.metrics_ts.create_index(
        [("meta.user_id", 1), ("meta.post_id", 1), ("ts", -1)]
    )
