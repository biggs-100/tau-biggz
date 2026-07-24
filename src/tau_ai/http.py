"""HTTP client creation for provider adapters."""

from __future__ import annotations

import httpx


def create_async_client(
    *,
    timeout: float = 120.0,
    proxy: str | None = None,
) -> httpx.AsyncClient:
    """Create an async HTTP client with optional proxy."""
    kwargs: dict = {"timeout": httpx.Timeout(timeout)}
    if proxy:
        kwargs["proxies"] = proxy
    return httpx.AsyncClient(**kwargs)
