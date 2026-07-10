"""TUI application runner functions extracted from app.py."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tau_coding.credentials import FileCredentialStore
from tau_coding.provider_config import (
    ProviderConfig,
    ProviderSelection,
    provider_has_usable_credentials,
    resolve_provider_selection,
)
from tau_coding.provider_runtime import create_model_provider
from tau_coding.session import CodingSession, CodingSessionConfig, ModelChoice, jsonl_session_storage
from tau_coding.session_manager import CodingSessionRecord, SessionManager
from tau_coding.shell_config import load_shell_settings
from tau_coding.thinking import DEFAULT_THINKING_LEVEL, ThinkingLevel
from tau_coding.tui.app import LoginRequiredProvider, TauTuiApp
from tau_coding.tui.config import load_tui_settings


def _explicit_resume_record(
    manager: SessionManager,
    *,
    session_id: str | None,
) -> CodingSessionRecord | None:
    if session_id is None:
        return None
    record = manager.get_session(session_id)
    if record is None:
        raise RuntimeError(f"Unknown session: {session_id}")
    return record


def _create_startup_session_record(
    manager: SessionManager,
    *,
    cwd: Path,
    selection: ProviderSelection,
) -> CodingSessionRecord:
    try:
        return manager.prepare_session(
            cwd=cwd,
            model=selection.model,
            provider_name=selection.provider.name,
        )
    except TypeError:
        return manager.prepare_session(cwd=cwd, model=selection.model)


def _resolve_tui_startup_selection(
    settings: Any,
    *,
    record: Any | None,
    provider_name: str | None,
    model: str | None,
    explicit_resume: bool,
    manager: Any | None = None,
    cwd: Path | None = None,
) -> ProviderSelection:
    if provider_name is not None or model is not None:
        return resolve_provider_selection(settings, provider_name=provider_name, model=model)

    if explicit_resume:
        record_selection = _selection_from_session_record(settings, record)
        if record_selection is not None:
            return record_selection

    default_selection = resolve_provider_selection(settings)
    if provider_has_usable_credentials(
        default_selection.provider,
        credential_reader=FileCredentialStore(),
    ):
        return default_selection

    # Try to restore provider/model from the latest session for this cwd
    if manager is not None and cwd is not None and not explicit_resume:
        latest = manager.latest_session_for_cwd(cwd)
        if latest is not None:
            latest_selection = _selection_from_session_record(settings, latest)
            if latest_selection is not None and provider_has_usable_credentials(
                latest_selection.provider,
                credential_reader=FileCredentialStore(),
            ):
                return latest_selection

    fallback_selection = _first_usable_startup_selection(settings)
    return fallback_selection or default_selection


def _resolve_startup_thinking_level(
    provider: ProviderConfig,
    model: str,
) -> ThinkingLevel:
    """Return a valid thinking level for the startup provider/model pair."""
    from tau_coding.provider_config import provider_default_thinking_level, provider_thinking_levels

    levels = provider_thinking_levels(provider, model=model)
    if not levels:
        return DEFAULT_THINKING_LEVEL
    preferred = provider_default_thinking_level(provider, model=model)
    if preferred and preferred in levels:
        return preferred
    if DEFAULT_THINKING_LEVEL in levels:
        return DEFAULT_THINKING_LEVEL
    return levels[0]


def _first_usable_startup_selection(settings: Any) -> ProviderSelection | None:
    credential_store = FileCredentialStore()
    for provider in settings.providers:
        if provider_has_usable_credentials(provider, credential_reader=credential_store):
            return ProviderSelection(provider=provider, model=provider.default_model)
    return None


def _selection_from_session_record(settings: Any, record: Any | None) -> ProviderSelection | None:
    if record is None:
        return None
    record_model = getattr(record, "model", None)
    if not isinstance(record_model, str) or not record_model:
        return None

    record_provider = getattr(record, "provider_name", None)
    if isinstance(record_provider, str) and record_provider:
        try:
            return resolve_provider_selection(
                settings,
                provider_name=record_provider,
                model=record_model,
            )
        except Exception:
            return None

    for choice in _usable_scoped_startup_choices(settings):
        if choice.model == record_model:
            return resolve_provider_selection(
                settings,
                provider_name=choice.provider_name,
                model=choice.model,
            )

    credential_store = FileCredentialStore()
    for provider in settings.providers:
        if record_model not in provider.models:
            continue
        if not provider_has_usable_credentials(provider, credential_reader=credential_store):
            continue
        return ProviderSelection(provider=provider, model=record_model)
    return None


def _usable_scoped_startup_choices(settings: Any) -> tuple[ModelChoice, ...]:
    credential_store = FileCredentialStore()
    choices: list[ModelChoice] = []
    for item in settings.scoped_models:
        try:
            provider = settings.get_provider(item.provider)
        except Exception:
            continue
        if item.model not in provider.models:
            continue
        if not provider_has_usable_credentials(provider, credential_reader=credential_store):
            continue
        choices.append(ModelChoice(provider_name=item.provider, model=item.model))
    return tuple(choices)


async def run_tui_app(
    *,
    model: str | None,
    cwd: Path,
    session_id: str | None = None,
    new_session: bool = False,
    provider_name: str | None = None,
    auto_compact_token_threshold: int | None = None,
    initial_prompt: str | None = None,
    session_manager: SessionManager | None = None,
    startup_notice: str | None = None,
    startup_notices: Sequence[str] = (),
    offline: bool = False,
) -> None:
    """Create the default provider/session and run the Textual app."""
    if new_session and session_id is not None:
        raise RuntimeError("--resume and --new-session cannot be used together")

    from tau_coding.provider_config import load_provider_settings
    provider_settings = load_provider_settings()
    # Auto-sync model metadata from models.dev on startup
    if not offline:
        try:
            from tau_coding.models_sync import sync_models

            _sync_result, _updated_settings = sync_models(provider_settings)
            if _updated_settings is not provider_settings:
                from tau_coding.provider_config import save_provider_settings
                save_provider_settings(_updated_settings, paths=None)
                provider_settings = load_provider_settings()
        except Exception:
            pass
    shell_settings = load_shell_settings()
    manager = session_manager or SessionManager()
    record = _explicit_resume_record(
        manager,
        session_id=session_id,
    )
    selection = _resolve_tui_startup_selection(
        provider_settings,
        record=record,
        provider_name=provider_name,
        model=model,
        explicit_resume=session_id is not None,
        manager=manager,
        cwd=cwd,
    )
    startup_message: str | None = None
    runtime_provider_config: ProviderConfig | None = selection.provider
    try:
        provider = create_model_provider(
            selection.provider,
            model=selection.model,
            thinking_level=_resolve_startup_thinking_level(selection.provider, selection.model),
        )
    except RuntimeError:
        login_required_message = (
            "Login required. Run /login to choose a provider, "
            f"or /login {selection.provider.name} to continue with the current provider."
        )
        startup_message = login_required_message
        provider = LoginRequiredProvider(startup_message)
        runtime_provider_config = None
    session: CodingSession | None = None
    try:
        index_on_first_persist = False
        if record is None:
            record = _create_startup_session_record(
                manager,
                cwd=cwd,
                selection=selection,
            )
            index_on_first_persist = manager.get_session(record.id) is None

        session = await CodingSession.load(
            CodingSessionConfig(
                provider=provider,
                model=record.model or selection.model,
                cwd=record.cwd,
                storage=jsonl_session_storage(record.path),
                session_id=record.id,
                session_manager=manager,
                provider_name=selection.provider.name,
                provider_settings=provider_settings,
                runtime_provider_config=runtime_provider_config,
                auto_compact_token_threshold=auto_compact_token_threshold,
                index_on_first_persist=index_on_first_persist,
                shell_command_prefix=shell_settings.shell_command_prefix,
            )
        )
        legacy_notices = (startup_notice,) if startup_notice else ()
        all_startup_notices = tuple((*startup_notices, *legacy_notices))
        app = TauTuiApp(
            session,
            tui_settings=load_tui_settings(),
            startup_message=startup_message,
            startup_notices=all_startup_notices,
            initial_prompt=initial_prompt,
        )
        await app.run_async()
    finally:
        if session is not None:
            close_session = getattr(session, "aclose", None)
            if close_session is not None:
                await close_session()
        await provider.aclose()
