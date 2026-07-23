# OAuth Provider Parity

## Scope

Add Anthropic Claude Pro/Max and GitHub Copilot OAuth flows to tau-biggz,
matching the existing OpenAI Codex OAuth pattern while sharing reusable
infrastructure.

## Architecture

```text
tau_coding/
  oauth_types.py       — shared dataclasses (OAuthProviderConfig, AuthMethod, etc.)
  oauth_registry.py    — provider → flow/refresh mappings
  oauth_device.py      — generic OAuth device-code flow server
  oauth_anthropic.py   — Anthropic Claude Pro/Max OAuth provider
  oauth_github_copilot.py — GitHub Copilot OAuth provider
  oauth.py             — refactored: parameterized _start_local_oauth_server,
                         OpenAICodexOAuthProvider class
  provider_catalog.py  — AuthMethod type, auth_methods field on entries
  provider_runtime.py  — OAuthRuntimeCredentialResolver for generic OAuth refresh
  credentials.py       — metadata field on OAuthCredential (backward compat)
```

## Auth Flows

| Provider | Kind | Grant Type | Device Code |
|---|---|---|---|
| OpenAI Codex | `openai-codex` | Authorization Code (PKCE) | Local server on port 1455 |
| Anthropic Claude Pro | `anthropic-oauth` | Authorization Code (PKCE) | Local server on port 1456 |
| GitHub Copilot | `github-copilot` | Device Code | Polling loop |

## Credential Changes

`OAuthCredential` gets `metadata: dict[str, JSONValue] = {}` with backward-
compat deserialization: existing JSON without `metadata` field still loads
correctly.

## TUI Routing

`_open_login()` uses `get_oauth_provider()` from `oauth_registry` instead of
`entry.kind == "openai-codex"` checks. Device code flow gets
`OAuthDeviceCodeScreen`.

## Token Refresh

`OAuthRuntimeCredentialResolver` is a generic callable that resolves and
auto-refreshes OAuth tokens for any OAuth provider type, replacing the
hard-coded `OpenAICodexCredentialResolver`.

## Implementation Order

1. Shared infrastructure: oauth_types, oauth_registry, oauth_device
2. Credentials: metadata field with backward-compat
3. OAuth providers: oauth_anthropic, oauth_github_copilot + refactored oauth.py
4. Runtime: provider_runtime resolver, provider_catalog auth_methods
5. TUI: app, app_helpers, screens_login updates
6. Catalog: catalog.toml updates
7. Tests
