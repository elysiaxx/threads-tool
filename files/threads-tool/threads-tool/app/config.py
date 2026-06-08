from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Threads Tool"
    environment: str = "dev"

    # MongoDB
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "threads_tool"

    # JWT
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # Token encryption (Fernet). Sinh bằng Fernet.generate_key().
    token_encryption_key: str = ""

    # Refresh token Threads trước khi hết hạn bao nhiêu ngày (token sống ~60 ngày).
    token_refresh_threshold_days: int = 7

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"

    # Storage (S3-compatible / MinIO)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "media"
    s3_public_base_url: str = "http://localhost:9000/media"

    # Frontend
    frontend_url: str = "http://localhost:5173"

    # Proxy (định tuyến outbound qua proxy theo account / pool xoay vòng)
    proxy_enabled: bool = False  # tắt -> mọi request đi trực tiếp như cũ
    proxy_apply_to_media: bool = True  # có định tuyến tải media (Collector) không
    proxy_test_url: str = "https://api.ipify.org?format=json"  # echo IP khi test

    # Threads OAuth (mọi giá trị đều cấu hình được để user tự thiết lập app)
    threads_client_id: str = ""
    threads_client_secret: str = ""
    threads_redirect_uri: str = "http://localhost:8000/api/accounts/oauth/threads/callback"
    threads_auth_base: str = "https://threads.net"
    threads_graph_base: str = "https://graph.threads.net"
    threads_scopes: str = "threads_basic,threads_content_publish,threads_manage_insights,threads_keyword_search"

    # Trend Radar — public web search (keyword/hashtag/link). Threads đổi doc_id
    # theo thời gian; lấy doc_id thật trong DevTools > Network > graphql của trang
    # search rồi đặt vào env. Để rỗng -> tính năng search báo lỗi rõ ràng (không vỡ).
    threads_search_doc_id: str = ""
    threads_search_friendly_name: str = "BarcelonaSearchResultsQuery"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
