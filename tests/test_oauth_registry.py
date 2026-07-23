"""Tests for tau_coding.oauth_registry module."""

from __future__ import annotations

import pytest

from tau_coding.oauth_registry import (
    get_oauth_provider,
    get_oauth_provider_names,
    get_oauth_providers_by_kind,
    register_core_oauth_providers,
    register_oauth_provider,
)
from tau_coding.oauth_types import OAuthProviderConfig


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    register_core_oauth_providers()


class TestRegisterOauthProvider:
    def test_register_and_get(self) -> None:
        config = OAuthProviderConfig(
            name="test-provider",
            kind="openai-codex",
            display_name="Test",
            client_id="cid",
            token_url="https://example.com/token",
        )
        register_oauth_provider(config)
        assert get_oauth_provider("test-provider") is config

    def test_get_nonexistent(self) -> None:
        assert get_oauth_provider("nonexistent") is None

    def test_register_core(self) -> None:
        register_core_oauth_providers()
        assert get_oauth_provider("openai-codex") is not None

    def test_get_provider_names(self) -> None:
        register_core_oauth_providers()
        names = get_oauth_provider_names()
        assert "openai-codex" in names

    def test_get_providers_by_kind(self) -> None:
        register_core_oauth_providers()
        providers = get_oauth_providers_by_kind("openai-codex")
        assert len(providers) >= 1
