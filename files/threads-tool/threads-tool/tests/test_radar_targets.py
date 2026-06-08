"""Test phần track theo keyword/hashtag/link của Trend Radar."""
import pytest

from app.modules.trends.service import (
    _normalize_target_value,
    _target_posts,
    normalize_session_cookie,
)
from app.services.threads_public import (
    _iter_posts,
    extract_search_doc_id_from_html,
    extract_posts_from_html,
    extract_shortcode,
)


def test_extract_posts_from_html_reads_script_json():
    html = (
        '<html><script type="application/json" data-sjs>'
        '{"a":{"thread_items":[{"post":{"pk":"99","code":"X"}}]}}'
        "</script>"
        '<script type="application/json">{"noise":1}</script></html>'
    )
    posts = extract_posts_from_html(html)
    assert [p["pk"] for p in posts] == ["99"]


def test_extract_posts_from_html_ignores_bad_json():
    html = '<script type="application/json">{thread_items not json}</script>'
    assert extract_posts_from_html(html) == []


def test_iter_posts_finds_nested_posts():
    data = {
        "searchResults": {
            "edges": [
                {"node": {"thread": {"thread_items": [{"post": {"pk": "1"}}]}}},
                {"node": {"thread": {"thread_items": [{"post": {"pk": "2"}}]}}},
            ]
        }
    }
    out: list[dict] = []
    _iter_posts(data, out)
    assert [p["pk"] for p in out] == ["1", "2"]


def test_iter_posts_handles_empty():
    out: list[dict] = []
    _iter_posts({"x": {"y": []}}, out)
    assert out == []


def test_extract_search_doc_id_from_html_near_friendly_name():
    html = (
        '<script>{"__dr":"BarcelonaSearchResultsQuery.graphql",'
        '"uri":"/api/graphql?doc_id=12345678901234567&variables={}"}</script>'
    )
    assert extract_search_doc_id_from_html(html) == {
        "doc_id": "12345678901234567",
        "friendly_name": "BarcelonaSearchResultsQuery",
    }


def test_extract_search_doc_id_from_html_returns_none_without_search_query():
    html = '<script>{"uri":"/api/graphql?doc_id=12345678901234567"}</script>'
    assert extract_search_doc_id_from_html(html) is None


def test_normalize_session_cookie_accepts_browser_export_json():
    raw = (
        '[{"name":"csrftoken","value":"csrf-secret","domain":".threads.com"},'
        '{"name":"mid","value":"mid-value","domain":".threads.com"},'
        '{"name":"sessionid","value":"session-secret","domain":".threads.com"},'
        '{"name":"ds_user_id","value":"123","domain":".threads.com"}]'
    )
    assert normalize_session_cookie(raw) == (
        "sessionid=session-secret; csrftoken=csrf-secret; "
        "ds_user_id=123; mid=mid-value"
    )


def test_normalize_session_cookie_rejects_export_without_sessionid():
    raw = '[{"name":"csrftoken","value":"csrf-secret"}]'
    with pytest.raises(ValueError) as exc:
        normalize_session_cookie(raw)
    assert "sessionid" in str(exc.value)
    assert "csrf-secret" not in str(exc.value)


def test_normalize_session_cookie_accepts_existing_header():
    raw = " sessionid=session-secret ; ds_user_id=123 ; csrftoken=csrf-secret "
    assert normalize_session_cookie(raw) == (
        "sessionid=session-secret; ds_user_id=123; csrftoken=csrf-secret"
    )


def test_normalize_session_cookie_rejects_bad_json_without_cookie_values():
    raw = '[{"name":"sessionid","value":"session-secret"}'
    with pytest.raises(ValueError) as exc:
        normalize_session_cookie(raw)
    assert "session-secret" not in str(exc.value)


def test_normalize_target_value_hashtag_prefix():
    assert _normalize_target_value("hashtag", "threadsvn") == "#threadsvn"
    assert _normalize_target_value("hashtag", "#threadsvn") == "#threadsvn"
    assert _normalize_target_value("keyword", "  ai marketing ") == "ai marketing"


def test_extract_shortcode_from_threads_url():
    assert extract_shortcode("https://www.threads.com/@user/post/AbC123") == "AbC123"
    assert extract_shortcode("AbC123_-") == "AbC123_-"
    assert extract_shortcode("12345") is None  # numeric id, không phải shortcode


class _FakeReader:
    def __init__(self):
        self.calls: list[tuple] = []

    async def search_posts(self, query, *, limit=25):
        self.calls.append(("search", query))
        return [{"id": "p"}]

    async def get_post(self, ref):
        self.calls.append(("get_post", ref))
        return {"id": "single"}


@pytest.mark.parametrize(
    "kind,value,expected",
    [
        ("keyword", "ai", ("search", "ai")),
        ("hashtag", "threadsvn", ("search", "#threadsvn")),
        ("link", "example.com", ("search", "example.com")),
        ("link", "https://www.threads.com/@u/post/AbC123", ("get_post", "https://www.threads.com/@u/post/AbC123")),
    ],
)
async def test_target_posts_routing(kind, value, expected):
    reader = _FakeReader()
    await _target_posts(reader, kind, value)
    assert reader.calls[0] == expected
