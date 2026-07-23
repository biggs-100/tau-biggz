"""Tests for tau_coding.oauth_types module."""

from __future__ import annotations

from tau_coding.oauth_types import OAuthProviderConfig


class TestOAuthProviderConfig:
    def test_default_values(self) -> None:
        config = OAuthProviderConfig(
            name="test",
            kind="openai-codex",
            display_name="Test Provider",
            client_id="cid",
            token_url="https://example.com/token",
        )
        assert config.name == "test"
        assert config.authorize_url is None
        assert config.grant_kind == "authorization_code"
        assert config.metadata == {}

    def test_with_all_fields(self) -> None:
        config = OAuthProviderConfig(
            name="full",
            kind="github-copilot",
            display_name="Full Provider",
            client_id="cid",
            token_url="https://example.com/token",
            authorize_url="https://example.com/auth",
            device_code_url="https://example.com/device",
            grant_kind="device_code",
            scopes="read",
            extra_auth_params={"prompt": "consent"},
            metadata={"version": 1},
        )
        assert config.grant_kind == "device_code"
        assert config.device_code_url == "https://example.com/device"
        assert config.metadata == {"version": 1}
