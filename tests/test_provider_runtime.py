import pytest

from tau_ai import OpenAICodexProvider
from tau_coding import provider_runtime
from tau_coding.credentials import FileCredentialStore, OAuthCredential
from tau_coding.provider_config import (
    AnthropicProviderConfig,
    OpenAICodexProviderConfig,
    OpenAICompatibleProviderConfig,
    ProviderConfigError,
)
from tau_coding.provider_runtime import (
    OpenAICodexCredentialResolver,
    _codex_reasoning_effort,
    create_model_provider,
)


def test_create_model_provider_returns_openai_codex_provider(tmp_path) -> None:
    store = FileCredentialStore(tmp_path / "credentials.json")

    provider = create_model_provider(
        OpenAICodexProviderConfig(),
        credential_store=store,
    )

    assert isinstance(provider, OpenAICodexProvider)


def test_create_model_provider_rejects_model_not_declared_for_provider(tmp_path) -> None:
    store = FileCredentialStore(tmp_path / "credentials.json")
    provider_config = OpenAICompatibleProviderConfig(
        name="local",
        models=("qwen",),
        default_model="qwen",
    )

    with pytest.raises(
        ProviderConfigError,
        match="Model is not configured for provider local: llama",
    ):
        create_model_provider(provider_config, credential_store=store, model="llama")


def test_create_model_provider_maps_codex_reasoning_effort_like_pi(tmp_path) -> None:
    store = FileCredentialStore(tmp_path / "credentials.json")
    provider_config = OpenAICodexProviderConfig(
        thinking_levels=("off", "minimal", "low", "medium", "high", "xhigh"),
        thinking_models=("gpt-5.5",),
        thinking_parameter="reasoning.effort",
    )

    off_provider = create_model_provider(
        provider_config,
        credential_store=store,
        model="gpt-5.5",
        thinking_level="off",
    )
    minimal_provider = create_model_provider(
        provider_config,
        credential_store=store,
        model="gpt-5.5",
        thinking_level="minimal",
    )
    xhigh_provider = create_model_provider(
        provider_config,
        credential_store=store,
        model="gpt-5.5",
        thinking_level="xhigh",
    )

    assert isinstance(off_provider, OpenAICodexProvider)
    assert isinstance(minimal_provider, OpenAICodexProvider)
    assert isinstance(xhigh_provider, OpenAICodexProvider)
    assert off_provider._config.reasoning_effort is None
    assert minimal_provider._config.reasoning_effort == "low"
    assert xhigh_provider._config.reasoning_effort == "xhigh"


@pytest.mark.anyio
async def test_openai_codex_credential_resolver_refreshes_expired_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = FileCredentialStore(tmp_path / "credentials.json")
    store.set_oauth(
        "openai-codex",
        OAuthCredential(
            access="old-access",
            refresh="old-refresh",
            expires=1,
            account_id="old-account",
        ),
    )

    async def fake_refresh(refresh_token: str) -> OAuthCredential:
        assert refresh_token == "old-refresh"
        return OAuthCredential(
            access="new-access",
            refresh="new-refresh",
            expires=9999999999999,
            account_id="new-account",
        )

    monkeypatch.setattr(provider_runtime, "refresh_openai_codex_token", fake_refresh)

    resolver = OpenAICodexCredentialResolver(
        OpenAICodexProviderConfig(),
        credential_store=store,
    )

    credentials = await resolver()

    assert credentials.access_token == "new-access"
    assert credentials.account_id == "new-account"
    assert store.get_oauth("openai-codex") == OAuthCredential(
        access="new-access",
        refresh="new-refresh",
        expires=9999999999999,
        account_id="new-account",
    )


def test_create_model_provider_returns_anthropic_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = FileCredentialStore(tmp_path / "credentials.json")
    mock_instance = object()

    monkeypatch.setattr(
        provider_runtime, "anthropic_config_from_provider", lambda *a, **kw: object()
    )
    monkeypatch.setattr(provider_runtime, "AnthropicProvider", lambda *a, **kw: mock_instance)

    result = create_model_provider(
        AnthropicProviderConfig(),
        credential_store=store,
    )

    assert result is mock_instance


def test_create_model_provider_returns_generic_openai_compatible_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = FileCredentialStore(tmp_path / "credentials.json")
    mock_instance = object()

    monkeypatch.setattr(
        provider_runtime,
        "openai_compatible_config_from_provider",
        lambda *a, **kw: object(),
    )
    monkeypatch.setattr(
        provider_runtime, "OpenAICompatibleProvider", lambda *a, **kw: mock_instance
    )

    result = create_model_provider(
        OpenAICompatibleProviderConfig(name="generic-test"),
        credential_store=store,
    )

    assert result is mock_instance


def test_codex_reasoning_effort_empty_levels_raises_error() -> None:
    provider = OpenAICodexProviderConfig(
        thinking_levels=("off", "low"),
        thinking_models=("gpt-5.5",),
        thinking_parameter="reasoning.effort",
    )

    with pytest.raises(
        ProviderConfigError,
        match="No thinking modes are available for openai-codex:gpt-5.3-codex",
    ):
        _codex_reasoning_effort(provider, model="gpt-5.3-codex", thinking_level="off")


def test_codex_reasoning_effort_invalid_level_raises_error() -> None:
    provider = OpenAICodexProviderConfig(
        thinking_levels=("off", "low"),
        thinking_models=("gpt-5.5",),
        thinking_parameter="reasoning.effort",
    )

    with pytest.raises(
        ProviderConfigError,
        match="Thinking mode high is not available for openai-codex:gpt-5.5",
    ):
        _codex_reasoning_effort(provider, model="gpt-5.5", thinking_level="high")


@pytest.mark.anyio
async def test_openai_codex_credential_resolver_env_var_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = FileCredentialStore(tmp_path / "credentials.json")
    monkeypatch.setenv("OPENAI_CODEX_ACCESS_TOKEN", "test-access-token")
    monkeypatch.setattr(
        provider_runtime,
        "account_id_from_access_token",
        lambda token: "test-account-id",
    )

    resolver = OpenAICodexCredentialResolver(
        OpenAICodexProviderConfig(),
        credential_store=store,
    )

    credentials = await resolver()

    assert credentials.access_token == "test-access-token"
    assert credentials.account_id == "test-account-id"


@pytest.mark.anyio
async def test_openai_codex_credential_resolver_no_credentials_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = FileCredentialStore(tmp_path / "credentials.json")
    monkeypatch.delenv("OPENAI_CODEX_ACCESS_TOKEN", raising=False)

    resolver = OpenAICodexCredentialResolver(
        OpenAICodexProviderConfig(),
        credential_store=store,
    )

    with pytest.raises(
        RuntimeError,
        match="Missing OpenAI Codex OAuth credentials",
    ):
        await resolver()
