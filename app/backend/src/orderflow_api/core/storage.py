from __future__ import annotations

from io import BytesIO
from typing import Any
from urllib.parse import urlparse

from orderflow_api.core.config import settings


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------
def _is_azure_blob() -> bool:
    return (settings.orderflow_api_storage_backend or "minio").strip().lower() == "azure_blob"


def _container_name() -> str:
    # ORDERFLOW_API_S3_BUCKET is reused for both backends so the deploy only
    # needs one knob for the location name.
    return settings.orderflow_api_s3_bucket


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------
def build_object_storage_client() -> Any:
    """
    Returns either a `minio.Minio` or an `azure.storage.blob.BlobServiceClient`
    depending on `ORDERFLOW_API_STORAGE_BACKEND`. Callers treat the value as
    opaque and pass it back into the helpers below.
    """
    if _is_azure_blob():
        conn_str = settings.orderflow_api_azure_storage_connection_string
        if not conn_str:
            raise RuntimeError(
                "ORDERFLOW_API_STORAGE_BACKEND=azure_blob but "
                "ORDERFLOW_API_AZURE_STORAGE_CONNECTION_STRING is not set."
            )
        from azure.storage.blob import BlobServiceClient

        return BlobServiceClient.from_connection_string(conn_str)

    from minio import Minio

    parsed = urlparse(settings.orderflow_api_s3_endpoint)
    endpoint = parsed.netloc or parsed.path
    secure = parsed.scheme == "https"

    return Minio(
        endpoint=endpoint,
        access_key=settings.orderflow_api_s3_access_key,
        secret_key=settings.orderflow_api_s3_secret_key,
        secure=secure,
    )


# ---------------------------------------------------------------------------
# Helpers (uniform surface across both backends)
# ---------------------------------------------------------------------------
def ensure_bucket_exists(client: Any) -> None:
    container = _container_name()

    if _is_azure_blob():
        from azure.core.exceptions import ResourceExistsError

        try:
            client.create_container(container)
        except ResourceExistsError:
            pass
        except Exception as exc:
            raise RuntimeError(f"Failed to ensure container exists: {exc}") from exc
        return

    try:
        if not client.bucket_exists(container):
            client.make_bucket(container)
    except Exception as exc:
        raise RuntimeError(f"Failed to ensure bucket exists: {exc}") from exc


def put_object(
    client: Any,
    object_key: str,
    payload: bytes,
    content_type: str | None,
) -> None:
    ensure_bucket_exists(client)
    container = _container_name()

    if _is_azure_blob():
        from azure.storage.blob import ContentSettings

        blob = client.get_blob_client(container=container, blob=object_key)
        blob.upload_blob(
            payload,
            overwrite=True,
            content_settings=ContentSettings(
                content_type=content_type or "application/octet-stream",
            ),
        )
        return

    stream = BytesIO(payload)
    client.put_object(
        bucket_name=container,
        object_name=object_key,
        data=stream,
        length=len(payload),
        content_type=content_type or "application/octet-stream",
    )


def get_object_bytes(client: Any, object_key: str) -> bytes:
    container = _container_name()

    if _is_azure_blob():
        blob = client.get_blob_client(container=container, blob=object_key)
        return blob.download_blob().readall()

    response = client.get_object(
        bucket_name=container,
        object_name=object_key,
    )
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
