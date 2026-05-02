from __future__ import annotations

from io import BytesIO
from urllib.parse import urlparse

from minio import Minio

from orderflow_api.core.config import settings


def build_object_storage_client() -> Minio:
    parsed = urlparse(settings.orderflow_api_s3_endpoint)
    endpoint = parsed.netloc or parsed.path
    secure = parsed.scheme == "https"

    return Minio(
        endpoint=endpoint,
        access_key=settings.orderflow_api_s3_access_key,
        secret_key=settings.orderflow_api_s3_secret_key,
        secure=secure,
    )


def ensure_bucket_exists(client: Minio) -> None:
    try:
        if not client.bucket_exists(settings.orderflow_api_s3_bucket):
            client.make_bucket(settings.orderflow_api_s3_bucket)
    except Exception as exc:
        raise RuntimeError(f"Failed to ensure bucket exists: {exc}") from exc


def put_object(
    client: Minio,
    object_key: str,
    payload: bytes,
    content_type: str | None,
) -> None:
    ensure_bucket_exists(client)
    stream = BytesIO(payload)
    client.put_object(
        bucket_name=settings.orderflow_api_s3_bucket,
        object_name=object_key,
        data=stream,
        length=len(payload),
        content_type=content_type or "application/octet-stream",
    )


def get_object_bytes(client: Minio, object_key: str) -> bytes:
    response = client.get_object(
        bucket_name=settings.orderflow_api_s3_bucket,
        object_name=object_key,
    )
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
