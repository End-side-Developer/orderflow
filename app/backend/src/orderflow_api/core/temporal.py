from __future__ import annotations

from typing import TYPE_CHECKING, Any

from orderflow_api.core.config import settings

if TYPE_CHECKING:
    from temporalio.client import Client

_temporal_client: Any | None = None


async def get_temporal_client() -> "Client":
    global _temporal_client

    if _temporal_client is None:
        from temporalio.client import Client

        _temporal_client = await Client.connect(
            settings.orderflow_api_temporal_host,
            namespace=settings.orderflow_api_temporal_namespace,
        )

    return _temporal_client


async def close_temporal_client() -> None:
    global _temporal_client

    if _temporal_client is not None:
        try:
            await _temporal_client.close()
        except Exception:
            pass
        finally:
            _temporal_client = None
