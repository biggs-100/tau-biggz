"""Anthropic Claude Pro/Max OAuth provider."""

from __future__ import annotations

import asyncio
import time
import webbrowser
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from tau_coding.credentials import OAuthCredential
from tau_coding.oauth import (
    OAuthAuthInfo,
    OAuthError,
    OAuthPrompt,
    TokenResponse,
    _optional_token_field,
    _required_token_field,
    _start_local_oauth_server,
    _token_expiry,
    _wait_for_authorization_code,
    create_authorization_flow,
    create_pkce_pair,
    parse_authorization_input,
)
from tau_coding.oauth_types import OAuthProviderConfig

ANTHROPIC_OAUTH_CLIENT_ID = "tau-claude-pro"
ANTHROPIC_OAUTH_AUTHORIZE_URL = "https://auth.anthropic.com/oauth/authorize"
ANTHROPIC_OAUTH_TOKEN_URL = "https://auth.anthropic.com/oauth/token"
ANTHROPIC_OAUTH_REDIRECT_URI = "http://localhost:1456/auth/callback"
ANTHROPIC_OAUTH_SCOPE = "openid profile email offline_access claude:pro"
ANTHROPIC_OAUTH_CALLBACK_PORT = 1456


async def login_anthropic_oauth(
    *,
    on_auth: Callable[[OAuthAuthInfo], None],
    on_prompt: Callable[[OAuthPrompt], Awaitable[str]],
    on_manual_code_input: Callable[[], Awaitable[str]] | None = None,
    on_progress: Callable[[str], None] | None = None,
    open_browser: bool = True,
    originator: str = "tau",
    client: httpx.AsyncClient | None = None,
    config: OAuthProviderConfig | None = None,
) -> OAuthCredential:
    """Run Anthropic OAuth and return refreshable credentials."""
    cid = (config and config.client_id) or ANTHROPIC_OAUTH_CLIENT_ID
    auth_url = (config and config.authorize_url) or ANTHROPIC_OAUTH_AUTHORIZE_URL
    redir = (config and config.redirect_uri) or ANTHROPIC_OAUTH_REDIRECT_URI
    scopes = (config and config.scopes) or ANTHROPIC_OAUTH_SCOPE
    port = (config and config.callback_port) or ANTHROPIC_OAUTH_CALLBACK_PORT
    tok_url = (config and config.token_url) or ANTHROPIC_OAUTH_TOKEN_URL
    extra = (config and config.extra_auth_params) or {}

    flow = create_authorization_flow(
        authorize_url=auth_url,
        client_id=cid,
        redirect_uri=redir,
        scopes=scopes,
        originator=originator,
        extra_params=extra,
    )
    server = await _start_local_oauth_server(flow.state, port=port, success_message="Anthropic")

    on_auth(
        OAuthAuthInfo(
            url=flow.url,
            instructions="A browser window should open. Complete Anthropic login to finish.",
        )
    )
    if open_browser:
        webbrowser.open(flow.url)

    try:
        code = await _wait_for_authorization_code(
            flow=flow,
            server=server,
            on_manual_code_input=on_manual_code_input,
        )
        if code is None:
            manual_input = await on_prompt(
                OAuthPrompt(message="Paste the authorization code or full redirect URL:")
            )
            parsed = parse_authorization_input(manual_input)
            code = parsed.code
        if not code:
            raise OAuthError("Missing authorization code")
        on_progress and on_progress("Exchanging authorization code...")
        token = await _exchange_anthropic_code(code, flow.verifier, cid, redir, tok_url, client=client)
        account_id = token.access.split(".")[0] if "." in token.access else "anthropic-oauth"
        return OAuthCredential(
            access=token.access,
            refresh=token.refresh,
            expires=token.expires,
            account_id=account_id,
            metadata={"provider": "anthropic-oauth"},
        )
    finally:
        if server is not None:
            server.close()


async def _exchange_anthropic_code(
    code: str,
    verifier: str,
    client_id: str,
    redirect_uri: str,
    token_url: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> TokenResponse:
    owns = client is None
    active = client or httpx.AsyncClient(timeout=60)
    try:
        resp = await active.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    finally:
        if owns:
            await active.aclose()

    if resp.status_code >= 400:
        raise OAuthError(f"Anthropic token exchange failed ({resp.status_code}): {resp.text}")
    raw = resp.json()
    if not isinstance(raw, dict):
        raise OAuthError("Anthropic token exchange response must be a JSON object")
    access = _required_token_field(raw, "access_token", action="anthropic-exchange")
    refresh = _required_token_field(raw, "refresh_token", action="anthropic-exchange")
    return TokenResponse(
        access=access,
        refresh=refresh,
        expires=_token_expiry(raw, access, action="anthropic-exchange"),
    )


async def refresh_anthropic_token(
    refresh_token: str,
    *,
    client: httpx.AsyncClient | None = None,
    config: OAuthProviderConfig | None = None,
) -> OAuthCredential:
    """Refresh Anthropic OAuth credentials."""
    tok_url = (config and config.token_url) or ANTHROPIC_OAUTH_TOKEN_URL
    cid = (config and config.client_id) or ANTHROPIC_OAUTH_CLIENT_ID

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
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    finally:
        if owns:
            await active.aclose()

    if resp.status_code >= 400:
        raise OAuthError(f"Anthropic token refresh failed ({resp.status_code}): {resp.text}")
    raw = resp.json()
    if not isinstance(raw, dict):
        raise OAuthError("Anthropic token refresh response must be a JSON object")
    access = _required_token_field(raw, "access_token", action="anthropic-refresh")
    next_refresh = _optional_token_field(raw, "refresh_token") or refresh_token
    account_id = "anthropic-oauth"
    return OAuthCredential(
        access=access,
        refresh=next_refresh,
        expires=_token_expiry(raw, access, action="anthropic-refresh"),
        account_id=account_id,
        metadata={"provider": "anthropic-oauth"},
    )
