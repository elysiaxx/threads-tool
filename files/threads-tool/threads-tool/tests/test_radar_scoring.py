"""Test chấm điểm xu hướng của Trend Radar (pure-function, không cần DB)."""
from datetime import datetime, timedelta, timezone

from app.models.trend_radar import RadarPost, RadarSettings
from app.modules.trends.service import (
    _engagement,
    _media_label,
    _passes,
    _score,
    _scored_post,
)


def test_engagement_applies_weights():
    s = RadarSettings(reply_weight=2.0, quote_weight=3.0)
    # 10 like + 5 reply*2 + 1 quote*3 = 23
    assert _engagement(10, 5, 1, s) == 23


def test_score_decays_with_age():
    s = RadarSettings(gravity=1.5)
    fresh = _score(100, age_hours=0, s=s)
    old = _score(100, age_hours=48, s=s)
    assert fresh > old > 0


def test_higher_gravity_penalizes_old_posts_more():
    eng, age = 100, 24
    low = _score(eng, age, RadarSettings(gravity=0.5))
    high = _score(eng, age, RadarSettings(gravity=3.0))
    assert low > high


def _post(**kw) -> RadarPost:
    base = dict(id="1", like_count=0, engagement=0, score=0, age_hours=1)
    base.update(kw)
    return RadarPost(**base)


def test_passes_respects_min_likes():
    s = RadarSettings(min_likes=10, min_score=0, max_age_hours=48)
    assert _passes(_post(like_count=20, engagement=20, score=5), s)
    assert not _passes(_post(like_count=5, engagement=5, score=5), s)


def test_passes_respects_max_age():
    s = RadarSettings(min_likes=0, min_score=0, max_age_hours=24)
    assert _passes(_post(score=1, age_hours=10), s)
    assert not _passes(_post(score=1, age_hours=100), s)


def test_passes_respects_min_score():
    s = RadarSettings(min_likes=0, min_score=2.0, max_age_hours=720)
    assert _passes(_post(score=3.0), s)
    assert not _passes(_post(score=1.0), s)


def test_media_label_mapping():
    assert _media_label(1) == "IMAGE"
    assert _media_label(2) == "VIDEO"
    assert _media_label(8) == "CAROUSEL"
    assert _media_label(19) == "TEXT"
    assert _media_label(123) == "OTHER"
    assert _media_label(None) == "TEXT"


def test_scored_post_computes_velocity_from_prev_snapshot():
    s = RadarSettings(reply_weight=2.0, quote_weight=3.0, gravity=1.5)
    now = datetime(2026, 6, 8, tzinfo=timezone.utc)
    doc = {
        "post_id": "p1",
        "like_count": 30,
        "reply_count": 0,
        "quote_count": 0,
        "taken_at": now - timedelta(hours=2),
        "collected_at": now,
        "prev_collected_at": now - timedelta(hours=1),
        "prev_like_count": 20,
        "prev_reply_count": 0,
        "prev_quote_count": 0,
        "author": {"username": "alice"},
    }
    p = _scored_post(doc, s, now)
    assert p.engagement == 30
    # (30 - 20) / 1h = 10 engagement/giờ
    assert p.velocity == 10.0
    assert p.age_hours == 2.0
    assert p.author.username == "alice"
    assert p.score > 0


def test_scored_post_velocity_none_without_prev():
    s = RadarSettings()
    now = datetime(2026, 6, 8, tzinfo=timezone.utc)
    doc = {"post_id": "p2", "like_count": 5, "collected_at": now, "author": {}}
    p = _scored_post(doc, s, now)
    assert p.velocity is None
