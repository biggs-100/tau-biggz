"""Tests for tau_coding.oauth_device module."""

from __future__ import annotations

import httpx
import pytest

from tau_coding.oauth_device import (
    DeviceCodeResponse,
    DeviceTokenResponse,
    OAuthDeviceCodeError,
    poll_device_token,
    start_device_code_flow,
)
from tau_coding.oauth_types import OAuthProviderConfig


@pytest.fixture
def device_config() -> OAuthProviderConfig:
    return OAuthProviderConfig(
        name="test-device",
        kind="github-copilot",
        display_name="Test Device",
        client_id="test-cid",
        token_url="https://example.com/token",
        device_code_url="https://example.com/device",
        grant_kind="device_code",
        scopes="read",
    )


@pytest.mark.anyio
async def test_start_device_code_flow_success(device_config: OAuthProviderConfig) -> None:
    resp = httpx.Response(
        200,
        json={
            "device_code": "dc123",
            "user_code": "ABC-123",
            "verification_uri": "https://example.com/verify",
            "interval": 5,
            "expires_in": 600,
        },
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    result = await start_device_code_flow(device_config, client=client)
    assert isinstance(result, DeviceCodeResponse)
    assert result.device_code == "dc123"
    assert result.user_code == "ABC-123"
    assert result.interval == 5


@pytest.mark.anyio
async def test_start_device_code_flow_http_error(device_config: OAuthProviderConfig) -> None:
    resp = httpx.Response(400, text="bad request")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    with pytest.raises(OAuthDeviceCodeError, match="Device code"):
        await start_device_code_flow(device_config, client=client)


@pytest.mark.anyio
async def test_poll_device_token_success(device_config: OAuthProviderConfig) -> None:
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(200, json={"error": "authorization_pending"})
        return httpx.Response(
            200,
            json={
                "access_token": "acc123",
                "refresh_token": "ref123",
                "expires_in": 3600,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await poll_device_token(
        device_config, "dc123", interval=0, client=client,
    )
    assert isinstance(result, DeviceTokenResponse)
    assert result.access == "acc123"
    assert result.refresh == "ref123"


@pytest.mark.anyio
async def test_poll_device_token_error(device_config: OAuthProviderConfig) -> None:
    resp = httpx.Response(200, json={"error": "access_denied"})
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    with pytest.raises(OAuthDeviceCodeError, match="access_denied"):
        await poll_device_token(device_config, "dc123", interval=0, client=client)
