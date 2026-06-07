"""
Unofficial public Threads reader.

This is intentionally separate from app.services.threads_api, which targets the
official Threads Graph API and requires OAuth tokens. The logic here follows the
fixed local fork of Danie1/threads-api but uses the app's existing httpx stack so
Docker does not need instagrapi or the archived package's dependency set.
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Literal, Optional

import httpx

THREADS_WEB_URL = "https://www.threads.com"
INSTAGRAM_TOKEN_URL = "https://www.instagram.com/instagram"

PROFILE_DOC_ID = "23996318473300828"
THREADS_TAB_DOC_ID = "6232751443445612"
REPLIES_TAB_DOC_ID = "6307072669391286"
POST_PAGE_DOC_ID = "5587632691339264"

DEFAULT_HEADERS = {
    "Authority": "www.threads.com",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": THREADS_WEB_URL,
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "X-ASBD-ID": "129477",
    "X-IG-App-ID": "238260118697367",
}


class ThreadsPublicError(RuntimeError):
    """Raised when the unofficial public reader cannot parse/use Threads data."""


def _parse_count(value: str | None) -> Optional[int]:
    if not value:
        return None

    value = value.strip().replace(",", "")
    match = re.match(r"^([\d.]+)\s*([KMB])?$", value, re.IGNORECASE)
    if not match:
        return None

    number = float(match.group(1))
    suffix = (match.group(2) or "").upper()
    multiplier = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suffix]
    return int(number * multiplier)


def _extract_meta_content(text: str, key: str) -> Optional[str]:
    meta_match = re.search(
        rf'<meta\b(?=[^>]*(?:property|name)=["\']{re.escape(key)}["\'])[^>]*>',
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not meta_match:
        return None

    content_match = re.search(
        r'content=(["\'])(.*?)\1',
        meta_match.group(0),
        re.IGNORECASE | re.DOTALL,
    )
    return html.unescape(content_match.group(2)) if content_match else None


def _timestamp(value: Optional[int]) -> Optional[str]:
    if not value:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _first_image_url(post: dict) -> Optional[str]:
    image_versions = post.get("image_versions2") or {}
    candidates = image_versions.get("candidates") or []
    if candidates:
        return candidates[0].get("url")

    carousel = post.get("carousel_media") or []
    if carousel:
        candidates = (carousel[0].get("image_versions2") or {}).get("candidates") or []
        if candidates:
            return candidates[0].get("url")
    return None


def _first_video_url(post: dict) -> Optional[str]:
    versions = post.get("video_versions") or []
    return versions[0].get("url") if versions else None


def _normalize_user(user: dict | None) -> dict:
    user = user or {}
    pk = user.get("pk") or user.get("pk_id")
    return {
        "id": str(pk) if pk is not None else None,
        "username": user.get("username"),
        "full_name": user.get("full_name"),
        "profile_pic_url": user.get("profile_pic_url"),
        "is_verified": user.get("is_verified"),
    }


def _normalize_post(post: dict, *, fallback_username: Optional[str] = None) -> dict:
    caption = post.get("caption") or {}
    user = post.get("user") or caption.get("user") or {}
    code = post.get("code")
    username = (user.get("username") or fallback_username or "").strip() or None
    permalink = f"{THREADS_WEB_URL}/@{username}/post/{code}" if username and code else None
    post_id = post.get("pk") or post.get("id")
    if isinstance(post_id, str) and "_" in post_id:
        post_id = post_id.split("_", 1)[0]

    text_app_info = post.get("text_post_app_info") or {}
    return {
        "id": str(post_id) if post_id is not None else None,
        "code": code,
        "permalink": permalink,
        "text": caption.get("text"),
        "taken_at": _timestamp(post.get("taken_at")),
        "media_type": post.get("media_type"),
        "like_count": post.get("like_count"),
        "reply_count": text_app_info.get("direct_reply_count"),
        "quote_count": text_app_info.get("quote_count"),
        "image_url": _first_image_url(post),
        "video_url": _first_video_url(post),
        "user": _normalize_user(user),
    }


def extract_public_profile_from_html(text: str, username: str) -> dict:
    text = html.unescape(text)
    username = username.strip().lstrip("@")

    user_id_match = re.search(r'"props":\{[^}]*"user_id":"(\d+)"', text)
    if not user_id_match:
        user_id_match = re.search(r'"user_id":"(\d+)"', text)
    user_id = user_id_match.group(1) if user_id_match else None

    title = _extract_meta_content(text, "og:title") or ""
    description = _extract_meta_content(text, "og:description") or ""
    profile_pic_url = _extract_meta_content(text, "og:image")

    full_name = None
    title_match = re.match(r"(.+?)\s+\(@[^)]+\)", title)
    if title_match:
        full_name = title_match.group(1).strip()

    username_match = re.search(r"\(@([^)]+)\)", title)
    if username_match:
        username = username_match.group(1).strip()

    follower_count = None
    media_count = None
    biography = None
    desc_match = re.match(
        r"([\d.,]+[KMB]?)\s+Followers?\s+•\s+([\d.,]+[KMB]?)\s+Threads?\s*(?:•\s+(.*?))?(?:\.\s+See\b|$)",
        description,
    )
    if desc_match:
        follower_count = _parse_count(desc_match.group(1))
        media_count = _parse_count(desc_match.group(2))
        if desc_match.group(3):
            biography = desc_match.group(3).strip()

    return {
        "threads_user_id": user_id,
        "username": username,
        "full_name": full_name,
        "follower_count": follower_count,
        "media_count": media_count,
        "biography": biography,
        "profile_pic_url": profile_pic_url,
    }


def extract_public_post_from_html(
    text: str,
    *,
    post_id: Optional[str] = None,
    shortcode: Optional[str] = None,
) -> dict:
    text = html.unescape(text)
    title = _extract_meta_content(text, "og:title") or ""
    description = (
        _extract_meta_content(text, "og:description")
        or _extract_meta_content(text, "description")
        or ""
    )
    image_url = _extract_meta_content(text, "og:image")

    title_match = re.match(r"(.+?)\s+\(@([^)]+)\)\s+on\s+Threads", title)
    full_name = title_match.group(1).strip() if title_match else None
    username = title_match.group(2).strip() if title_match else None

    post_id_match = re.search(r'"post_id":"(\d+)"', text)
    owner_id_match = re.search(r'"owner_id_for_crawlers":"(\d+)"', text)
    shortcode_match = re.search(r"(?:shortcode=|/post/)([A-Za-z0-9_-]+)", text)

    post_id = post_id or (post_id_match.group(1) if post_id_match else None)
    owner_id = owner_id_match.group(1) if owner_id_match else None
    shortcode = shortcode or (shortcode_match.group(1) if shortcode_match else None)
    permalink = f"{THREADS_WEB_URL}/@{username}/post/{shortcode}" if username and shortcode else None

    return {
        "id": post_id,
        "code": shortcode,
        "permalink": permalink,
        "text": description,
        "taken_at": None,
        "media_type": None,
        "like_count": None,
        "reply_count": None,
        "quote_count": None,
        "image_url": image_url,
        "video_url": None,
        "user": {
            "id": owner_id,
            "username": username,
            "full_name": full_name,
            "profile_pic_url": image_url,
            "is_verified": None,
        },
    }


def extract_shortcode(post_ref: str) -> Optional[str]:
    if not post_ref:
        return None

    post_ref = str(post_ref).strip()
    for marker in ("/post/", "/t/"):
        if marker in post_ref:
            return post_ref.split(marker, 1)[1].split("?", 1)[0].split("/", 1)[0]

    if re.match(r"^[A-Za-z0-9_-]+$", post_ref) and not post_ref.isdigit():
        return post_ref
    return None


class ThreadsPublicClient:
    def __init__(self, proxy: Optional[str] = None, timeout: float = 30):
        self._proxy = proxy
        self._timeout = timeout
        self._lsd_token: Optional[str] = None
        self._post_cache_by_id: dict[str, dict] = {}
        self._post_cache_by_shortcode: dict[str, dict] = {}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            follow_redirects=True,
            timeout=self._timeout,
            proxy=self._proxy,
        )

    async def _get_text(self, url: str, headers: Optional[dict] = None) -> str:
        async with self._client() as client:
            resp = await client.get(url, headers=headers or DEFAULT_HEADERS)
            resp.raise_for_status()
            return resp.text

    async def _refresh_public_token(self) -> str:
        if self._lsd_token:
            return self._lsd_token

        headers = dict(DEFAULT_HEADERS)
        headers.pop("X-FB-LSD", None)
        text = await self._get_text(INSTAGRAM_TOKEN_URL, headers=headers)

        token_match = re.search(r'LSD",\[\],\{"token":"(.*?)"\},\d+\]', text)
        if not token_match:
            token_match = re.search(r'"LSD",\[\],\{"token":"(.*?)"\}', text)
        if not token_match:
            raise ThreadsPublicError("Không lấy được public LSD token từ Instagram")

        self._lsd_token = token_match.group(1)
        return self._lsd_token

    async def _public_headers(self) -> dict:
        headers = dict(DEFAULT_HEADERS)
        token = await self._refresh_public_token()
        headers["X-FB-LSD"] = token
        headers["x-fb-lsd"] = token
        return headers

    async def _graphql(self, friendly_name: str, variables: dict, doc_id: str) -> dict:
        token = await self._refresh_public_token()
        headers = await self._public_headers()
        headers.update(
            {
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "x-fb-friendly-name": friendly_name,
            }
        )
        payload = {
            "lsd": token,
            "variables": json.dumps(variables),
            "doc_id": doc_id,
        }
        async with self._client() as client:
            resp = await client.post(f"{THREADS_WEB_URL}/api/graphql", headers=headers, data=payload)
            resp.raise_for_status()
            data = resp.json()

        if data.get("errors"):
            raise ThreadsPublicError(str(data["errors"]))
        return data

    def _cache_posts(self, posts: list[dict]) -> None:
        for post in posts:
            if post.get("id"):
                self._post_cache_by_id[str(post["id"])] = post
            if post.get("code"):
                self._post_cache_by_shortcode[post["code"]] = post

    async def get_profile_by_username(self, username: str) -> dict:
        username = username.strip().lstrip("@")
        if not username:
            raise ThreadsPublicError("username không được rỗng")

        quoted = urllib.parse.quote(username, safe="")
        html_text = await self._get_text(f"{THREADS_WEB_URL}/@{quoted}", headers=await self._public_headers())
        profile = extract_public_profile_from_html(html_text, username)
        if not profile.get("threads_user_id"):
            raise ThreadsPublicError(f"Không tìm thấy user_id cho @{username}")
        return profile

    async def get_profile_by_user_id(self, user_id: str, username: Optional[str] = None) -> dict:
        if username:
            return await self.get_profile_by_username(username)

        try:
            data = await self._graphql(
                "BarcelonaProfileRootQuery",
                {"userID": user_id},
                PROFILE_DOC_ID,
            )
            user = (data.get("data") or {}).get("userData", {}).get("user")
            if user:
                return {
                    "threads_user_id": str(user.get("pk") or user.get("pk_id") or user_id),
                    "username": user.get("username"),
                    "full_name": user.get("full_name"),
                    "follower_count": user.get("follower_count"),
                    "media_count": user.get("media_count"),
                    "biography": user.get("biography"),
                    "profile_pic_url": user.get("profile_pic_url"),
                }
        except Exception as exc:  # noqa: BLE001
            raise ThreadsPublicError(
                "Public lookup theo user_id không ổn định; hãy truyền username"
            ) from exc

        raise ThreadsPublicError("Không đọc được profile public")

    async def get_user_id_from_username(self, username: str) -> str:
        profile = await self.get_profile_by_username(username)
        return profile["threads_user_id"]

    async def list_user_posts(
        self,
        user_id: str,
        *,
        username: Optional[str] = None,
        kind: Literal["threads", "replies"] = "threads",
        limit: int = 25,
    ) -> list[dict]:
        friendly_name = (
            "BarcelonaProfileRepliesTabQuery"
            if kind == "replies"
            else "BarcelonaProfileThreadsTabQuery"
        )
        doc_id = REPLIES_TAB_DOC_ID if kind == "replies" else THREADS_TAB_DOC_ID
        data = await self._graphql(friendly_name, {"userID": user_id}, doc_id)
        media_data = (data.get("data") or {}).get("mediaData") or {}
        threads = media_data.get("threads") or []

        posts: list[dict] = []
        for thread in threads:
            for item in thread.get("thread_items") or []:
                post = item.get("post")
                if post:
                    posts.append(_normalize_post(post, fallback_username=username))
                    break
            if len(posts) >= limit:
                break

        self._cache_posts(posts)
        return posts

    async def get_post(self, post_ref: str) -> dict:
        post_ref = str(post_ref)
        shortcode = extract_shortcode(post_ref)
        cached = self._post_cache_by_id.get(post_ref)
        if not cached and shortcode:
            cached = self._post_cache_by_shortcode.get(shortcode)
        if cached:
            return cached

        try:
            data = await self._graphql(
                "BarcelonaPostPageQuery",
                {"postID": post_ref},
                POST_PAGE_DOC_ID,
            )
            post_data = (data.get("data") or {}).get("data")
            if post_data:
                containing = post_data.get("containing_thread") or {}
                for item in containing.get("thread_items") or []:
                    if item.get("post"):
                        post = _normalize_post(item["post"])
                        self._cache_posts([post])
                        return post
        except Exception:
            pass

        if not shortcode:
            raise ThreadsPublicError(
                "Không đọc được post theo numeric id; hãy truyền Threads URL hoặc shortcode"
            )

        quoted = urllib.parse.quote(shortcode, safe="")
        html_text = await self._get_text(f"{THREADS_WEB_URL}/t/{quoted}", headers=await self._public_headers())
        post = extract_public_post_from_html(html_text, shortcode=shortcode)
        self._cache_posts([post])
        return post
