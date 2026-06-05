"""
Storage S3-compatible (MinIO dev / R2 / S3 prod). Tách theo prefix
media/{user_id}/... để gọn khi xóa/đổi gói một user (điểm cách ly #4).
Threads API tự fetch media từ public URL nên bucket phải public-read.
"""
import boto3

from app.config import settings


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )


def object_key(user_id: str, filename: str) -> str:
    return f"{user_id}/{filename}"


def public_url(key: str) -> str:
    return f"{settings.s3_public_base_url.rstrip('/')}/{key}"


def upload_bytes(user_id: str, filename: str, data: bytes, content_type: str) -> str:
    """Upload và trả về public URL (dùng bởi Collector)."""
    key = object_key(user_id, filename)
    client = get_s3_client()
    client.put_object(
        Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type
    )
    return public_url(key)
