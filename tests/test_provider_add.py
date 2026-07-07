"""Tests for the ``tau providers add`` CLI command."""

from __future__ import annotations

from pathlib import Path

from tau_coding.catalog_loader import user_catalog_path
from tau_coding.credentials import FileCredentialStore, credentials_path
from tau_coding.paths import TauPaths
from tau_coding.provider_add import providers_add_command
from tau_coding.provider_config import load_provider_settings


class TestProvidersAddCli:
    """Test that ``providers_add_command`` creates valid catalog entries."""

    def test_add_openai_compatible_provider(self, tmp_path: Path, monkeypatch) -> None:
        """Simulate interactive input and verify the provider is saved."""
        tau_home = tmp_path / ".tau"
        tau_home.mkdir()
        paths = TauPaths(home=tau_home)

        answers = iter([
            "my-provider",       # name
            "My Provider",       # display name
            "1",                 # kind (openai-compatible)
            "https://api.test.com/v1",  # base URL
            "MY_API_KEY",        # api_key_env
            "model-a, model-b",  # models
            "model-a",           # default model
            "",                  # API key (none)
        ])
        monkeypatch.setattr("tau_coding.provider_add.typer.prompt", lambda msg, **kw: next(answers))
        monkeypatch.setattr("tau_coding.provider_add.typer.echo", lambda msg, **kw: None)
        monkeypatch.setattr("tau_coding.provider_add.typer.confirm", lambda msg, **kw: True)

        providers_add_command(paths=paths)

        catalog_path = user_catalog_path(paths)
        assert catalog_path.exists(), "Catalog file was not created"
        raw = catalog_path.read_text(encoding="utf-8")
        assert "my-provider" in raw
        assert "My Provider" in raw
        assert "https://api.test.com/v1" in raw
        assert "model-a" in raw

    def test_add_anthropic_provider(self, tmp_path: Path, monkeypatch) -> None:
        """Adding an anthropic-kind provider should work via the CLI."""
        tau_home = tmp_path / ".tau"
        tau_home.mkdir()
        paths = TauPaths(home=tau_home)

        answers = iter([
            "my-claude",         # name
            "My Claude",         # display name
            "2",                 # kind (anthropic)
            "https://api.test.com/v1",  # base URL
            "MY_CLAUDE_KEY",     # api_key_env
            "claude-v1",         # models
            "claude-v1",         # default model
            "sk-secret",         # API key
        ])
        monkeypatch.setattr("tau_coding.provider_add.typer.prompt", lambda msg, **kw: next(answers))
        monkeypatch.setattr("tau_coding.provider_add.typer.echo", lambda msg, **kw: None)
        monkeypatch.setattr("tau_coding.provider_add.typer.confirm", lambda msg, **kw: True)

        providers_add_command(paths=paths)

        # API key should be stored
        store = FileCredentialStore(path=credentials_path(paths))
        assert store.get("my-claude") == "sk-secret"

        # Provider should be loadable
        settings = load_provider_settings(paths)
        provider = settings.get_provider("my-claude")
        assert provider is not None
        assert provider.name == "my-claude"
