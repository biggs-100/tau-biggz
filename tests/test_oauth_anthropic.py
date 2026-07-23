"""Tests for tau_coding.oauth_anthropic module."""

from __future__ import annotations

import httpx
import pytest

from tau_coding.oauth import TokenResponse
from tau_coding.oauth_anthropic import _exchange_anthropic_code, refresh_anthropic_token


@pytest.mark.anyio
async def test_exchange_code_success() -> None:
    resp = httpx.Response(
        200,
        json={
            "access_token": "acc_tok",
            "refresh_token": "ref_tok",
            "expires_in": 3600,
        },
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    result = await _exchange_anthropic_code(
        "code", "verifier", "cid", "http://localhost/redirect", "https://example.com/token",
        client=client,
    )
    assert isinstance(result, TokenResponse)
    assert result.access == "acc_tok"
    assert result.refresh == "ref_tok"


@pytest.mark.anyio
async def test_exchange_code_http_error() -> None:
    resp = httpx.Response(400, text="bad")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    with pytest.raises(RuntimeError, match="Anthropic"):
        await _exchange_anthropic_code(
            "c", "v", "cid", "http://localhost/r", "https://example.com/t",
            client=client,
        )


@pytest.mark.anyio
async def test_refresh_success() -> None:
    resp = httpx.Response(
        200,
        json={"access_token": "acc_new", "expires_in": 3600},
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    result = await refresh_anthropic_token("old_refresh", client=client)
    assert result.access == "acc_new"
    assert result.account_id == "anthropic-oauth"
