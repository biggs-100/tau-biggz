"""GitHub Copilot OAuth provider using device-code flow."""

from __future__ import annotations

import asyncio
import time
import webbrowser
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from tau_coding.credentials import OAuthCredential
from tau_coding.oauth import OAuthAuthInfo, OAuthError, OAuthPrompt
from tau_coding.oauth_device import (
    DeviceTokenResponse,
    poll_device_token,
    start_device_code_flow,
)
from tau_coding.oauth_types import OAuthProviderConfig

GITHUB_COPILOT_CLIENT_ID = "tau-github-copilot"
GITHUB_COPILOT_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_COPILOT_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_COPILOT_SCOPE = "read:user repo"
GITHUB_COPILOT_AUDIENCE = "https://api.github.com"


async def login_github_copilot(
    *,
    on_auth: Callable[[OAuthAuthInfo], None],
    on_prompt: Callable[[OAuthPrompt], Awaitable[str]],
    on_progress: Callable[[str], None] | None = None,
    open_browser: bool = True,
    client: httpx.AsyncClient | None = None,
    config: OAuthProviderConfig | None = None,
) -> OAuthCredential:
    """Run GitHub Copilot device-code OAuth and return refreshable credentials."""
    cid = (config and config.client_id) or GITHUB_COPILOT_CLIENT_ID
    dc_url = (config and config.device_code_url) or GITHUB_COPILOT_DEVICE_CODE_URL
    tok_url = (config and config.token_url) or GITHUB_COPILOT_TOKEN_URL
    scopes = (config and config.scopes) or GITHUB_COPILOT_SCOPE

    provider_config = OAuthProviderConfig(
        name="github-copilot",
        kind="github-copilot",
        display_name="GitHub Copilot",
        client_id=cid,
        token_url=tok_url,
        device_code_url=dc_url,
        grant_kind="device_code",
        scopes=scopes,
    )

    device_resp = await start_device_code_flow(provider_config, client=client)

    on_auth(
        OAuthAuthInfo(
            url=device_resp.verification_uri,
            instructions=(
                f"Open {device_resp.verification_uri} and enter code: {device_resp.user_code}"
            ),
        )
    )
    if open_browser:
        webbrowser.open(device_resp.verification_uri)

    on_progress and on_progress(
        f"Waiting for device code authorization at {device_resp.verification_uri}..."
    )

    token: DeviceTokenResponse = await poll_device_token(
        provider_config,
        device_resp.device_code,
        interval=device_resp.interval,
        client=client,
    )

    refresh_token = token.refresh or ""
    account_id = _github_account_id_from_token(token.access)

    return OAuthCredential(
        access=token.access,
        refresh=refresh_token,
        expires=token.expires,
        account_id=account_id or "github-copilot",
        metadata={"provider": "github-copilot"},
    )


async def refresh_github_copilot_token(
    refresh_token: str,
    *,
    client: httpx.AsyncClient | None = None,
    config: OAuthProviderConfig | None = None,
) -> OAuthCredential:
    """Refresh GitHub Copilot OAuth credentials."""
    tok_url = (config and config.token_url) or GITHUB_COPILOT_TOKEN_URL
    cid = (config and config.client_id) or GITHUB_COPILOT_CLIENT_ID

    owns = client is None
    active = client or httpx.AsyncClient(timeout=60)
    try:
        resp = await active.post(
            tok_url,
            data={
                "grant_type": "refresh_token",
                "client_id": cid,
                "refresh_token": refresh_token,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
    finally:
        if owns:
            await active.aclose()

    if resp.status_code >= 400:
        raise OAuthError(f"GitHub Copilot token refresh failed ({resp.status_code}): {resp.text}")
    raw = resp.json()
    if not isinstance(raw, dict):
        raise OAuthError("GitHub Copilot token refresh response must be a JSON object")
    access = raw.get("access_token")
    if not isinstance(access, str) or not access:
        raise OAuthError("Missing access_token in GitHub Copilot refresh response")
    next_refresh = raw.get("refresh_token", refresh_token)
    next_refresh_str = str(next_refresh) if isinstance(next_refresh, str) and next_refresh else refresh_token
    expires_in = raw.get("expires_in", 3600)
    expires = int(time.time() * 1000) + int(expires_in * 1000)
    account_id = _github_account_id_from_token(access) or "github-copilot"
    return OAuthCredential(
        access=access,
        refresh=next_refresh_str,
        expires=expires,
        account_id=account_id,
        metadata={"provider": "github-copilot"},
    )


def _github_account_id_from_token(access_token: str) -> str | None:
    if access_token.startswith("ghu_") or access_token.startswith("gho_"):
        return "github-copilot"
    return None
