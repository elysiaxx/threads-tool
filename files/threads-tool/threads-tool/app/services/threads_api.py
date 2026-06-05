"""
Client gọi Threads Graph API (đọc dữ liệu: posts, insights, keyword search).
Tách khỏi services/oauth/threads.py vốn chỉ lo cấp/đổi token.

LƯU Ý: tên endpoint/metric dựa trên Threads Graph API được tài liệu hóa, NÊN
đối chiếu lại docs hiện hành trước khi chạy thật (API còn đổi nhanh). Ràng buộc:
- insights chỉ có dữ liệu từ 2024-04-13; demographics cần >100 followers.
- keyword_search bị giới hạn tần suất rất gắt -> cache mạnh, poll thưa.
"""
from typing import Optional

import httpx

from app.config import settings

# Metric theo từng post (media) và theo cấp tài khoản (user).
MEDIA_METRICS = ["views", "likes", "replies", "reposts", "quotes", "shares"]
USER_METRICS = ["views", "likes", "replies", "reposts", "quotes", "followers_count"]

_THREAD_FIELDS = "id,permalink,timestamp,media_type,text,shortcode"


def _parse_insights(payload: dict) -> dict:
    """
    Chuẩn hóa response insights -> {metric_name: value}.
    Threads trả mỗi metric dạng total_value.value (lifetime) hoặc values[].value.
    """
    out: dict[str, int] = {}
    for item in payload.get("data", []):
        name = item.get("name")
        if not name:
            continue
        if "total_value" in item:
            out[name] = int(item["total_value"].get("value", 0) or 0)
        elif item.get("values"):
            out[name] = int(item["values"][-1].get("value", 0) or 0)
    return out


class ThreadsApiClient:
    def __init__(
        self,
        access_token: str,
        base_url: Optional[str] = None,
        proxy: Optional[str] = None,
    ):
        self._token = access_token
        self._base = base_url or settings.threads_graph_base
        self._proxy = proxy  # None -> đi trực tiếp

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base, timeout=30, proxy=self._proxy)

    async def _get(self, path: str, params: dict) -> dict:
        params = {**params, "access_token": self._token}
        async with self._client() as client:
            resp = await client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, params: dict) -> dict:
        # Graph API nhận tham số POST qua query string; bỏ giá trị None.
        params = {k: v for k, v in params.items() if v is not None}
        params["access_token"] = self._token
        async with self._client() as client:
            resp = await client.post(path, params=params)
            resp.raise_for_status()
            return resp.json()

    async def list_threads(self, threads_user_id: str, limit: int = 25) -> list[dict]:
        """Danh sách post của tài khoản owned."""
        data = await self._get(
            f"/{threads_user_id}/threads",
            {"fields": _THREAD_FIELDS, "limit": limit},
        )
        return data.get("data", [])

    async def media_insights(self, media_id: str) -> dict:
        """Insights của 1 post -> {metric: value}."""
        data = await self._get(
            f"/{media_id}/insights", {"metric": ",".join(MEDIA_METRICS)}
        )
        return _parse_insights(data)

    async def user_insights(self, threads_user_id: str) -> dict:
        """Insights cấp tài khoản (gồm followers_count) -> {metric: value}."""
        data = await self._get(
            f"/{threads_user_id}/threads_insights",
            {"metric": ",".join(USER_METRICS)},
        )
        return _parse_insights(data)

    async def keyword_search(self, query: str, search_type: str = "TOP") -> list[dict]:
        """Tìm post theo keyword (rate-limit gắt). search_type: TOP | RECENT."""
        data = await self._get(
            "/keyword_search",
            {"q": query, "search_type": search_type, "fields": _THREAD_FIELDS},
        )
        return data.get("data", [])

    # --- Publishing (2 bước: tạo container -> publish) ----------------------
    async def create_container(
        self,
        threads_user_id: str,
        *,
        media_type: str,
        text: Optional[str] = None,
        image_url: Optional[str] = None,
        video_url: Optional[str] = None,
        children: Optional[list[str]] = None,
        is_carousel_item: bool = False,
    ) -> str:
        """Tạo media container, trả về creation_id (id container)."""
        data = await self._post(
            f"/{threads_user_id}/threads",
            {
                "media_type": media_type,
                "text": text,
                "image_url": image_url,
                "video_url": video_url,
                "children": ",".join(children) if children else None,
                "is_carousel_item": "true" if is_carousel_item else None,
            },
        )
        return data["id"]

    async def container_status(self, container_id: str) -> dict:
        """Trạng thái xử lý container: {status, error_message}. Video cần FINISHED."""
        return await self._get(
            f"/{container_id}", {"fields": "status,error_message"}
        )

    async def publish_container(self, threads_user_id: str, creation_id: str) -> str:
        """Publish container đã sẵn sàng, trả về id post đã đăng."""
        data = await self._post(
            f"/{threads_user_id}/threads_publish", {"creation_id": creation_id}
        )
        return data["id"]

    async def get_media(self, media_id: str) -> dict:
        """Lấy metadata 1 post (permalink, timestamp…)."""
        return await self._get(f"/{media_id}", {"fields": _THREAD_FIELDS})
