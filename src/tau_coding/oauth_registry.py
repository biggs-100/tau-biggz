from __future__ import annotations

from tau_coding.oauth_types import OAuthProviderConfig, OAuthProviderKind
from tau_coding.oauth import (
    OpenAICodexOAuthProvider,
    exchange_openai_codex_authorization_code,
    refresh_openai_codex_token,
)
from tau_coding.oauth_anthropic import (
    ANTHROPIC_OAUTH_AUTHORIZE_URL,
    ANTHROPIC_OAUTH_CALLBACK_PORT,
    ANTHROPIC_OAUTH_CLIENT_ID,
    ANTHROPIC_OAUTH_REDIRECT_URI,
    ANTHROPIC_OAUTH_SCOPE,
    ANTHROPIC_OAUTH_TOKEN_URL,
    login_anthropic_oauth,
    refresh_anthropic_token,
)
from tau_coding.oauth_github_copilot import (
    GITHUB_COPILOT_CLIENT_ID,
    GITHUB_COPILOT_DEVICE_CODE_URL,
    GITHUB_COPILOT_TOKEN_URL,
    login_github_copilot,
    refresh_github_copilot_token,
)

_OAUTH_PROVIDERS: dict[str, OAuthProviderConfig] = {}


def register_oauth_provider(config: OAuthProviderConfig) -> None:
    _OAUTH_PROVIDERS[config.name] = config


def get_oauth_provider(name: str) -> OAuthProviderConfig | None:
    return _OAUTH_PROVIDERS.get(name)


def get_oauth_providers_by_kind(
    kind: OAuthProviderKind,
) -> list[OAuthProviderConfig]:
    return [p for p in _OAUTH_PROVIDERS.values() if p.kind == kind]


def get_oauth_provider_names() -> tuple[str, ...]:
    return tuple(_OAUTH_PROVIDERS)


def register_core_oauth_providers() -> None:
    register_oauth_provider(
        OAuthProviderConfig(
            name="openai-codex",
            kind="openai-codex",
            display_name="OpenAI Codex",
            client_id=OpenAICodexOAuthProvider.client_id,
            authorize_url=OpenAICodexOAuthProvider.authorize_url,
            token_url=OpenAICodexOAuthProvider.token_url,
            scopes=OpenAICodexOAuthProvider.scopes,
            redirect_uri=OpenAICodexOAuthProvider.redirect_uri,
            callback_port=OpenAICodexOAuthProvider.callback_port,
            grant_kind="authorization_code",
            account_claim=OpenAICodexOAuthProvider.account_claim,
            extra_auth_params={
                "id_token_add_organizations": "true",
                "codex_cli_simplified_flow": "true",
            },
        )
    )

    register_oauth_provider(
        OAuthProviderConfig(
            name="anthropic",
            kind="anthropic-oauth",
            display_name="Anthropic Claude Pro",
            client_id=ANTHROPIC_OAUTH_CLIENT_ID,
            authorize_url=ANTHROPIC_OAUTH_AUTHORIZE_URL,
            token_url=ANTHROPIC_OAUTH_TOKEN_URL,
            scopes=ANTHROPIC_OAUTH_SCOPE,
            redirect_uri=ANTHROPIC_OAUTH_REDIRECT_URI,
            callback_port=ANTHROPIC_OAUTH_CALLBACK_PORT,
            grant_kind="authorization_code",
            account_claim="sub",
        )
    )

    register_oauth_provider(
        OAuthProviderConfig(
            name="github-copilot",
            kind="github-copilot",
            display_name="GitHub Copilot",
            client_id=GITHUB_COPILOT_CLIENT_ID,
            authorize_url=GITHUB_COPILOT_DEVICE_CODE_URL,
            token_url=GITHUB_COPILOT_TOKEN_URL,
            scopes=("read:user",),
            grant_kind="device_code",
            account_claim="sub",
        )
    )


__all__ = [
    "get_oauth_provider",
    "get_oauth_provider_names",
    "get_oauth_providers_by_kind",
    "register_core_oauth_providers",
    "register_oauth_provider",
]
