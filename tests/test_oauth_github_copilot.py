"""Tests for tau_coding.oauth_github_copilot module."""

from __future__ import annotations

import httpx
import pytest

from tau_coding.oauth_github_copilot import (
    _github_account_id_from_token,
    refresh_github_copilot_token,
)


@pytest.mark.anyio
async def test_refresh_success() -> None:
    resp = httpx.Response(
        200,
        json={"access_token": "ghu_newtoken", "expires_in": 3600},
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    result = await refresh_github_copilot_token("old_refresh", client=client)
    assert result.access == "ghu_newtoken"
    assert result.account_id == "github-copilot"


@pytest.mark.anyio
async def test_refresh_with_new_refresh() -> None:
    resp = httpx.Response(
        200,
        json={
            "access_token": "gho_token",
            "refresh_token": "new_refresh",
            "expires_in": 3600,
        },
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    result = await refresh_github_copilot_token("old_refresh", client=client)
    assert result.refresh == "new_refresh"


@pytest.mark.anyio
async def test_refresh_http_error() -> None:
    resp = httpx.Response(401, text="unauthorized")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    with pytest.raises(RuntimeError, match="GitHub"):
        await refresh_github_copilot_token("r", client=client)


class TestGithubAccountIdFromToken:
    def test_ghu_prefix(self) -> None:
        assert _github_account_id_from_token("ghu_abc") == "github-copilot"

    def test_gho_prefix(self) -> None:
        assert _github_account_id_from_token("gho_abc") == "github-copilot"

    def test_unknown_prefix(self) -> None:
        assert _github_account_id_from_token("unknown_token") is None

    def test_empty(self) -> None:
        assert _github_account_id_from_token("") is None
