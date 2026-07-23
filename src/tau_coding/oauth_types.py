from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from tau_agent.types import JSONValue

OAuthGrantKind = Literal["authorization_code", "device_code"]
OAuthProviderKind = Literal["openai-codex", "anthropic-oauth", "github-copilot"]


@dataclass(frozen=True, slots=True)
class OAuthProviderConfig:
    name: str
    kind: OAuthProviderKind
    display_name: str
    client_id: str
    token_url: str
    authorize_url: str | None = None
    scopes: str = ""
    redirect_uri: str | None = None
    callback_port: int | None = None
    grant_kind: OAuthGrantKind = "authorization_code"
    device_code_url: str | None = None
    audience: str | None = None
    account_claim: str | None = None
    extra_auth_params: dict[str, str] = field(default_factory=dict)
    extra_token_params: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)
