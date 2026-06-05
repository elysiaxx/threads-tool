"""
Provider cho Threads. Luồng chuẩn:
  1. authorize_url -> user cấp quyền
  2. exchange_code -> short-lived token -> đổi sang long-lived (~60 ngày)
  3. refresh -> gia hạn long-lived token

LƯU Ý: tên endpoint/tham số dựa trên luồng Threads/Meta Graph được tài liệu hóa,
NÊN đối chiếu lại với docs hiện hành trước khi chạy thật (API còn thay đổi nhanh).
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.services.oauth.base import OAuthTokens

_SIXTY_DAYS = 60 * 24 * 3600


class ThreadsOAuthProvider:
    name = "threads"

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": settings.threads_client_id,
            "redirect_uri": settings.threads_redirect_uri,
            "scope": settings.threads_scopes,
            "response_type": "code",
            "state": state,
        }
        return f"{settings.threads_auth_base}/oauth/authorize?{urlencode(params)}"

    async def exchange_code(self, code: str, proxy: str | None = None) -> OAuthTokens:
        async with httpx.AsyncClient(
            base_url=settings.threads_graph_base, timeout=30, proxy=proxy
        ) as client:
            # 1) short-lived token
            short = await client.post(
                "/oauth/access_token",
                data={
                    "client_id": settings.threads_client_id,
                    "client_secret": settings.threads_client_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.threads_redirect_uri,
                    "code": code,
                },
            )
            short.raise_for_status()
            sdata = short.json()
            short_token = sdata["access_token"]
            external_user_id = str(sdata.get("user_id", "")) or None

            # 2) đổi sang long-lived (~60 ngày)
            long = await client.get(
                "/access_token",
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
        async with httpx.AsyncClient(
            base_url=settings.threads_graph_base, timeout=30, proxy=proxy
        ) as client:
            resp = await client.get(
                "/refresh_access_token",
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
