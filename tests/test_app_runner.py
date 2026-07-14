"""Tests for TUI app runner startup orchestration."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tau_coding.provider_config import ProviderSelection
from tau_coding.tui import app_runner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(**kwargs: object) -> SimpleNamespace:
    """Create a fake provider config with defaults overridable via kwargs."""
    attrs: dict[str, object] = {
        "name": "test-provider",
        "models": ("model-a", "model-b"),
        "default_model": "model-a",
        "credential_name": None,
        "api_key_env": "TEST_API_KEY",
    }
    attrs.update(kwargs)
    return SimpleNamespace(**attrs)


def _make_settings(
    providers: list[SimpleNamespace] | None = None,
    default_provider: str = "test-provider",
    scoped_models: tuple = (),
) -> SimpleNamespace:
    """Create fake provider settings."""
    providers = providers or [_make_provider()]
    provider_map = {p.name: p for p in providers}

    def _get_provider(name: str | None = None) -> SimpleNamespace:
        target = name or default_provider
        return provider_map[target]

    return SimpleNamespace(
        default_provider=default_provider,
        providers=providers,
        scoped_models=scoped_models,
        get_provider=_get_provider,
    )


def _make_session_record(**kwargs: object) -> SimpleNamespace:
    """Create a fake CodingSessionRecord."""
    attrs: dict[str, object] = {
        "id": "test-session-id",
        "path": Path("/tmp/test.jsonl"),
        "cwd": Path("/workspace"),
        "model": "model-a",
        "title": None,
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "provider_name": None,
    }
    attrs.update(kwargs)
    return SimpleNamespace(**attrs)


# ---------------------------------------------------------------------------
# _explicit_resume_record
# ---------------------------------------------------------------------------


class TestExplicitResumeRecord:
    """Tests for ``_explicit_resume_record``."""

    def test_unknown_session_raises(self) -> None:
        """When session_id is not found, RuntimeError is raised."""
        manager = MagicMock()
        manager.get_session.return_value = None

        with pytest.raises(RuntimeError, match=r"Unknown session: nonexistent"):
            app_runner._explicit_resume_record(manager, session_id="nonexistent")


# ---------------------------------------------------------------------------
# _resolve_tui_startup_selection
# ---------------------------------------------------------------------------


class TestResolveTuiStartupSelection:
    """Tests for ``_resolve_tui_startup_selection``."""

    def test_explicit_provider_model_returns_choice(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit provider_name/model bypasses all other resolution."""
        settings = _make_settings()
        expected = ProviderSelection(
            provider=_make_provider(name="custom"),
            model="model-x",
        )

        monkeypatch.setattr(
            app_runner,
            "resolve_provider_selection",
            lambda s, **kw: expected,
        )

        result = app_runner._resolve_tui_startup_selection(
            settings,
            record=None,
            provider_name="custom",
            model="model-x",
            explicit_resume=False,
        )

        assert result is expected

    def test_default_provider_with_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default selection is returned when its provider has credentials."""
        settings = _make_settings()
        expected = ProviderSelection(
            provider=settings.providers[0],
            model="model-a",
        )

        monkeypatch.setattr(
            app_runner,
            "resolve_provider_selection",
            lambda s, **kw: expected,
        )
        monkeypatch.setattr(
            app_runner,
            "provider_has_usable_credentials",
            lambda p, **kw: True,
        )

        result = app_runner._resolve_tui_startup_selection(
            settings,
            record=None,
            provider_name=None,
            model=None,
            explicit_resume=False,
        )

        assert result is expected

    def test_no_credentialled_providers_falls_back_to_first_usable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When default provider lacks credentials, first usable is returned."""
        settings = _make_settings()
        default_selection = ProviderSelection(provider=settings.providers[0], model="model-a")
        fallback_provider = _make_provider(name="fallback", models=("model-b",))
        fallback_selection = ProviderSelection(provider=fallback_provider, model="model-b")

        monkeypatch.setattr(
            app_runner,
            "resolve_provider_selection",
            lambda s, **kw: default_selection,
        )
        monkeypatch.setattr(
            app_runner,
            "provider_has_usable_credentials",
            lambda p, **kw: False,
        )
        monkeypatch.setattr(
            app_runner,
            "_first_usable_startup_selection",
            lambda s: fallback_selection,
        )

        result = app_runner._resolve_tui_startup_selection(
            settings,
            record=None,
            provider_name=None,
            model=None,
            explicit_resume=False,
        )

        assert result is fallback_selection

    def test_latest_session_record_used_when_default_lacks_creds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Latest session record is used when default has no credentials."""
        settings = _make_settings()
        default_selection = ProviderSelection(provider=settings.providers[0], model="model-a")
        latest_record = _make_session_record(model="model-a", provider_name="latest")
        latest_provider = _make_provider(name="latest", models=("model-a",))
        latest_selection = ProviderSelection(provider=latest_provider, model="model-a")

        manager = MagicMock()
        manager.latest_session_for_cwd.return_value = latest_record

        call_count: list[int] = [0]

        def _has_creds(provider: object, **kw: object) -> bool:
            call_count[0] += 1
            # First call (default) → False, later calls (latest) → True
            return call_count[0] > 1

        monkeypatch.setattr(
            app_runner,
            "resolve_provider_selection",
            lambda s, **kw: default_selection,
        )
        monkeypatch.setattr(app_runner, "provider_has_usable_credentials", _has_creds)
        monkeypatch.setattr(
            app_runner,
            "_selection_from_session_record",
            lambda s, record: latest_selection if record is latest_record else None,
        )

        result = app_runner._resolve_tui_startup_selection(
            settings,
            record=None,
            provider_name=None,
            model=None,
            explicit_resume=False,
            manager=manager,
            cwd=Path("/workspace"),
        )

        assert result is latest_selection
        manager.latest_session_for_cwd.assert_called_once_with(Path("/workspace"))


# ---------------------------------------------------------------------------
# _selection_from_session_record
# ---------------------------------------------------------------------------


class TestSelectionFromSessionRecord:
    """Tests for ``_selection_from_session_record``."""

    def test_valid_record_matches_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Record with provider_name and model resolves to matching selection."""
        provider = _make_provider(
            name="matched-provider", models=("model-a",), default_model="model-a"
        )
        settings = _make_settings(providers=[provider])
        record = _make_session_record(model="model-a", provider_name="matched-provider")
        expected = ProviderSelection(provider=provider, model="model-a")

        def _mock_resolve(s: object, **kw: str | None) -> ProviderSelection:
            assert kw.get("provider_name") == "matched-provider"
            assert kw.get("model") == "model-a"
            return expected

        monkeypatch.setattr(app_runner, "resolve_provider_selection", _mock_resolve)

        result = app_runner._selection_from_session_record(settings, record)

        assert result is expected

    def test_no_matching_provider_returns_first_usable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Record without a matching provider_name falls through to first usable."""
        provider = _make_provider(name="fallback", models=("model-a",), default_model="model-a")
        settings = _make_settings(providers=[provider])
        record = _make_session_record(model="model-a", provider_name=None)

        monkeypatch.setattr(app_runner, "_usable_scoped_startup_choices", lambda s: ())
        monkeypatch.setattr(
            app_runner,
            "provider_has_usable_credentials",
            lambda p, **kw: True,
        )

        result = app_runner._selection_from_session_record(settings, record)

        assert result is not None
        assert result.model == "model-a"
        assert result.provider is provider


# ---------------------------------------------------------------------------
# _resolve_startup_thinking_level
# ---------------------------------------------------------------------------


class TestResolveStartupThinkingLevel:
    """Tests for ``_resolve_startup_thinking_level``."""

    def test_preferred_level_in_levels_returns_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the default thinking level is available, it is returned."""
        provider = _make_provider()

        monkeypatch.setattr(
            "tau_coding.provider_config.provider_thinking_levels",
            lambda provider, **kw: ("off", "low", "medium", "high"),
        )
        monkeypatch.setattr(
            "tau_coding.provider_config.provider_default_thinking_level",
            lambda provider, **kw: "low",
        )

        result = app_runner._resolve_startup_thinking_level(provider, "model-a")

        assert result == "low"

    def test_default_thinking_level_not_in_levels_returns_first(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When DEFAULT_THINKING_LEVEL is absent, the first level is returned."""
        provider = _make_provider()

        monkeypatch.setattr(
            "tau_coding.provider_config.provider_thinking_levels",
            lambda provider, **kw: ("off", "low"),
        )
        monkeypatch.setattr(
            "tau_coding.provider_config.provider_default_thinking_level",
            lambda provider, **kw: None,
        )

        result = app_runner._resolve_startup_thinking_level(provider, "model-a")

        assert result == "off"
