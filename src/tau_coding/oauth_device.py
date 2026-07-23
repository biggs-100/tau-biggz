from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from tau_coding.oauth_types import OAuthProviderConfig


class OAuthDeviceCodeError(RuntimeError):
    """Raised when a device-code flow cannot complete."""


@dataclass(frozen=True, slots=True)
class DeviceCodeResponse:
    device_code: str
    user_code: str
    verification_uri: str
    interval: int
    expires_in: int


@dataclass(frozen=True, slots=True)
class DeviceTokenResponse:
    access: str
    refresh: str | None
    expires: int


async def start_device_code_flow(
    config: OAuthProviderConfig,
    *,
    client: httpx.AsyncClient | None = None,
) -> DeviceCodeResponse:
    owns = client is None
    active = client or httpx.AsyncClient(timeout=30)
    try:
        resp = await active.post(
            config.device_code_url or "",
            data={
                "client_id": config.client_id,
                "scope": config.scopes,
                **config.extra_token_params,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    finally:
        if owns:
            await active.aclose()

    if resp.status_code >= 400:
        raise OAuthDeviceCodeError(
            f"Device code request failed ({resp.status_code}): {resp.text}"
        )
    raw = resp.json()
    return DeviceCodeResponse(
        device_code=_device_str(raw, "device_code"),
        user_code=_device_str(raw, "user_code"),
        verification_uri=_device_str(raw, "verification_uri"),
        interval=raw.get("interval", 5),
        expires_in=int(raw["expires_in"]),
    )


async def poll_device_token(
    config: OAuthProviderConfig,
    device_code: str,
    *,
    interval: int = 5,
    timeout_seconds: int = 600,
    client: httpx.AsyncClient | None = None,
) -> DeviceTokenResponse:
    owns = client is None
    active = client or httpx.AsyncClient(timeout=30)
    start = time.monotonic()
    try:
        while True:
            elapsed = time.monotonic() - start
            if elapsed > timeout_seconds:
                raise OAuthDeviceCodeError("Device code flow timed out")

            await asyncio.sleep(interval)
            resp = await active.post(
                config.token_url,
                data={
                    "client_id": config.client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            raw = resp.json()
            if not isinstance(raw, dict):
                raise OAuthDeviceCodeError("Device token response must be a JSON object")

            error = raw.get("error")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval = min(interval + 5, 60)
                continue
            if error:
                raise OAuthDeviceCodeError(f"Device code error: {error}")

            access = raw.get("access_token")
            if not isinstance(access, str) or not access:
                raise OAuthDeviceCodeError("Missing access_token in device token response")

            refresh = raw.get("refresh_token")
            refresh_str: str | None = refresh if isinstance(refresh, str) and refresh else None
            expires_in = raw.get("expires_in", 3600)
            expires = int(time.time() * 1000) + int(expires_in * 1000)

            return DeviceTokenResponse(access=access, refresh=refresh_str, expires=expires)
    finally:
        if owns:
            await active.aclose()


def _device_str(raw: dict[str, Any], field: str) -> str:
    val = raw.get(field)
    if not isinstance(val, str) or not val:
        raise OAuthDeviceCodeError(f"Missing {field} in device code response")
    return val
