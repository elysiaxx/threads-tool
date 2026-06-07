from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.routes import accounts as accounts_route
from app.services.oauth.base import OAuthTokens


class FakeDb:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "accounts"
        return self.collection


class FakeProvider:
    def __init__(self):
        self.exchange_code = AsyncMock(
            return_value=OAuthTokens(
                access_token="long-token",
                expires_at=datetime(2026, 6, 7, tzinfo=timezone.utc),
                external_user_id="threads-user-1",
                username="threader",
            )
        )


@pytest.mark.asyncio
async def test_oauth_callback_without_code_is_probeable():
    response = await accounts_route.oauth_callback(
        "threads", code=None, state=None, db=FakeDb(MagicMock())
    )

    assert response == {"status": "ok", "platform": "threads"}


@pytest.mark.asyncio
async def test_oauth_callback_exchanges_code_through_proxy_pool(monkeypatch):
    provider = FakeProvider()
    collection = MagicMock()
    collection.update_one = AsyncMock()
    db = FakeDb(collection)

    monkeypatch.setattr(accounts_route, "verify_state_token", lambda state: "user-1")
    monkeypatch.setattr(accounts_route, "get_provider", lambda platform: provider)
    monkeypatch.setattr(accounts_route, "encrypt_token", lambda token: f"enc:{token}")
    monkeypatch.setattr(
        accounts_route.proxy_service,
        "pick_from_pool",
        AsyncMock(return_value="socks5://proxy.local:1080"),
    )

    response = await accounts_route.oauth_callback(
        "threads", code="auth-code", state="signed-state", db=db
    )

    accounts_route.proxy_service.pick_from_pool.assert_awaited_once_with(db, "user-1")
    provider.exchange_code.assert_awaited_once_with(
        "auth-code", proxy="socks5://proxy.local:1080"
    )
    collection.update_one.assert_awaited_once()
    query, update = collection.update_one.call_args.args[:2]
    assert query == {
        "platform": "threads",
        "type": "owned",
        "threads_user_id": "threads-user-1",
        "user_id": "user-1",
    }
    assert update["$set"]["access_token_enc"] == "enc:long-token"
    assert update["$set"]["username"] == "threader"
    assert update["$setOnInsert"]["user_id"] == "user-1"
    assert collection.update_one.call_args.kwargs["upsert"] is True
    assert response.status_code == 307
