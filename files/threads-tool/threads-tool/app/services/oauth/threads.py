"""
Provider cho Threads dùng Authlib làm OAuth 2 client. Luồng chuẩn:
  1. authorize_url -> user cấp quyền
  2. exchange_code -> short-lived token -> đổi sang long-lived (~60 ngày)
  3. refresh -> gia hạn long-lived token

Threads vẫn bắt buộc dùng authorization server/token endpoint của Meta để cấp token
cho API chính thức; Authlib thay phần tự build URL và tự exchange OAuth code.
"""
from datetime import datetime, timedelta, timezone

from authlib.integrations.httpx_client import AsyncOAuth2Client, OAuth2Client

from app.config import settings
from app.services.oauth.base import OAuthTokens

_SIXTY_DAYS = 60 * 24 * 3600


class ThreadsOAuthProvider:
    name = "threads"

    @property
    def _authorization_endpoint(self) -> str:
        return f"{settings.threads_auth_base.rstrip('/')}/oauth/authorize"

    @property
    def _token_endpoint(self) -> str:
        return f"{settings.threads_graph_base.rstrip('/')}/oauth/access_token"

    @property
    def _long_lived_token_endpoint(self) -> str:
        return f"{settings.threads_graph_base.rstrip('/')}/access_token"

    @property
    def _refresh_endpoint(self) -> str:
        return f"{settings.threads_graph_base.rstrip('/')}/refresh_access_token"

    def _oauth_client(self, proxy: str | None = None) -> AsyncOAuth2Client:
        client = AsyncOAuth2Client(
            client_id=settings.threads_client_id,
            client_secret=settings.threads_client_secret,
            redirect_uri=settings.threads_redirect_uri,
            scope=settings.threads_scopes,
            token_endpoint_auth_method="client_secret_post",
            timeout=30,
            proxy=proxy,
        )
        client.register_compliance_hook(
            "access_token_response", self._ensure_token_type
        )
        return client

    @staticmethod
    def _ensure_token_type(resp):
        data = resp.json()
        if "access_token" in data and "token_type" not in data:
            data = {**data, "token_type": "bearer"}
            resp.json = lambda: data
        return resp

    def authorize_url(self, state: str) -> str:
        with OAuth2Client(
            client_id=settings.threads_client_id,
            redirect_uri=settings.threads_redirect_uri,
            scope=settings.threads_scopes,
        ) as client:
            url, _ = client.create_authorization_url(
                self._authorization_endpoint,
                response_type="code",
                state=state,
            )
            return url

    async def exchange_code(self, code: str, proxy: str | None = None) -> OAuthTokens:
        async with self._oauth_client(proxy=proxy) as client:
            short_data = await client.fetch_token(
                self._token_endpoint,
                grant_type="authorization_code",
                code=code,
                redirect_uri=settings.threads_redirect_uri,
            )

        short_token = short_data["access_token"]
        external_user_id = str(short_data.get("user_id", "")) or None

        async with self._oauth_client(proxy=proxy) as client:
            # Threads dùng grant_type riêng cho bước đổi short-lived -> long-lived.
            long = await client.get(
                self._long_lived_token_endpoint,
                params={
                    "grant_type": "th_exchange_token",
                    "client_secret": settings.threads_client_secret,
                    "access_token": short_token,
                },
            )
            long.raise_for_status()
            ldata = long.json()
            expires_in = int(ldata.get("expires_in", _SIXTY_DAYS))
            return OAuthTokens(
                access_token=ldata.get("access_token", short_token),
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
                external_user_id=external_user_id,
            )

    async def refresh(self, access_token: str, proxy: str | None = None) -> OAuthTokens:
        async with self._oauth_client(proxy=proxy) as client:
            resp = await client.get(
                self._refresh_endpoint,
                params={
                    "grant_type": "th_refresh_token",
                    "access_token": access_token,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            expires_in = int(data.get("expires_in", _SIXTY_DAYS))
            return OAuthTokens(
                access_token=data["access_token"],
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            )
