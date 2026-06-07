from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from app.config import settings
from app.services.oauth.threads import ThreadsOAuthProvider


class FakeResponse:
    def __init__(self, data: dict):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self) -> dict:
        return self._data


class FakeAsyncOAuth2Client:
    calls: list[tuple[str, str, dict]] = []
    tokens: list[dict] = []
    responses: list[dict] = []
    init_kwargs: list[dict] = []
    compliance_hooks: list[tuple[str, object]] = []

    def __init__(self, **kwargs):
        self.init_kwargs.append(kwargs)

    def register_compliance_hook(self, hook_type: str, hook):
        self.compliance_hooks.append((hook_type, hook))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def fetch_token(self, url: str, **kwargs):
        self.calls.append(("fetch_token", url, kwargs))
        return self.tokens.pop(0)

    async def get(self, url: str, params: dict):
        self.calls.append(("get", url, params))
        return FakeResponse(self.responses.pop(0))


@pytest.fixture(autouse=True)
def reset_fake_client(monkeypatch):
    FakeAsyncOAuth2Client.calls = []
    FakeAsyncOAuth2Client.tokens = []
    FakeAsyncOAuth2Client.responses = []
    FakeAsyncOAuth2Client.init_kwargs = []
    FakeAsyncOAuth2Client.compliance_hooks = []
    monkeypatch.setattr(
        "app.services.oauth.threads.AsyncOAuth2Client", FakeAsyncOAuth2Client
    )


@pytest.fixture(autouse=True)
def threads_settings(monkeypatch):
    monkeypatch.setattr(settings, "threads_client_id", "client-id")
    monkeypatch.setattr(settings, "threads_client_secret", "client-secret")
    monkeypatch.setattr(
        settings,
        "threads_redirect_uri",
        "https://example.test/api/accounts/oauth/threads/callback",
    )
    monkeypatch.setattr(settings, "threads_auth_base", "https://threads.net")
    monkeypatch.setattr(settings, "threads_graph_base", "https://graph.threads.net")
    monkeypatch.setattr(
        settings,
        "threads_scopes",
        "threads_basic,threads_content_publish",
    )


def test_authorize_url_uses_authlib_client():
    url = ThreadsOAuthProvider().authorize_url("signed-state")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == (
        "https://threads.net/oauth/authorize"
    )
    assert query["client_id"] == ["client-id"]
    assert query["redirect_uri"] == [
        "https://example.test/api/accounts/oauth/threads/callback"
    ]
    assert query["response_type"] == ["code"]
    assert query["state"] == ["signed-state"]
    assert query["scope"] == ["threads_basic,threads_content_publish"]


def test_token_response_hook_adds_missing_token_type():
    response = FakeResponse({"access_token": "short-token", "user_id": "u1"})

    fixed = ThreadsOAuthProvider._ensure_token_type(response)

    assert fixed.json() == {
        "access_token": "short-token",
        "user_id": "u1",
        "token_type": "bearer",
    }


@pytest.mark.asyncio
async def test_exchange_code_uses_authlib_for_oauth_step():
    FakeAsyncOAuth2Client.tokens = [
        {"access_token": "short-token", "user_id": 12345}
    ]
    FakeAsyncOAuth2Client.responses = [
        {"access_token": "long-token", "expires_in": 3600}
    ]

    tokens = await ThreadsOAuthProvider().exchange_code("auth-code", proxy="socks5://p")

    assert tokens.access_token == "long-token"
    assert tokens.external_user_id == "12345"
    assert isinstance(tokens.expires_at, datetime)
    assert tokens.expires_at.tzinfo == timezone.utc
    assert FakeAsyncOAuth2Client.init_kwargs[0]["proxy"] == "socks5://p"
    assert FakeAsyncOAuth2Client.compliance_hooks[0][0] == "access_token_response"
    assert FakeAsyncOAuth2Client.calls[0] == (
        "fetch_token",
        "https://graph.threads.net/oauth/access_token",
        {
            "grant_type": "authorization_code",
            "code": "auth-code",
            "redirect_uri": "https://example.test/api/accounts/oauth/threads/callback",
        },
    )
    assert FakeAsyncOAuth2Client.calls[1] == (
        "get",
        "https://graph.threads.net/access_token",
        {
            "grant_type": "th_exchange_token",
            "client_secret": "client-secret",
            "access_token": "short-token",
        },
    )


@pytest.mark.asyncio
async def test_refresh_uses_threads_refresh_endpoint():
    FakeAsyncOAuth2Client.responses = [
        {"access_token": "refreshed-token", "expires_in": 3600}
    ]

    tokens = await ThreadsOAuthProvider().refresh("old-token")

    assert tokens.access_token == "refreshed-token"
    assert isinstance(tokens.expires_at, datetime)
    assert FakeAsyncOAuth2Client.calls == [
        (
            "get",
            "https://graph.threads.net/refresh_access_token",
            {"grant_type": "th_refresh_token", "access_token": "old-token"},
        )
    ]
