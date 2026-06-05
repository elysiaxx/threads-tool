"""
Storage S3-compatible (MinIO dev / R2 / S3 prod). Tách theo prefix
media/{user_id}/... để gọn khi xóa/đổi gói một user (điểm cách ly #4).
Threads API tự fetch media từ public URL nên bucket phải public-read.
"""
import json
import logging

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )


def ensure_bucket() -> None:
    """
    Tạo bucket nếu chưa có và set policy public-read (Threads API tự fetch media
    từ public URL nên object phải đọc được ẩn danh). Gọi lúc API khởi động;
    lỗi không làm sập app — chỉ log để vẫn chạy được khi storage tạm chưa sẵn sàng.
    """
    client = get_s3_client()
    bucket = settings.s3_bucket
    try:
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError:
            client.create_bucket(Bucket=bucket)
            logger.info("Đã tạo bucket '%s'", bucket)

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                }
            ],
        }
        client.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
    except Exception as exc:  # noqa: BLE001 - không chặn startup nếu storage lỗi
        logger.warning("Không thể bootstrap bucket '%s': %s", bucket, exc)


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
