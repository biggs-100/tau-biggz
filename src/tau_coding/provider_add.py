"""Interactive CLI command to add a custom provider to Tau.

Usage::

    tau providers add

Prompts for provider details and saves to ``~/.tau/catalog.toml``.
"""

from __future__ import annotations

import typer

from tau_coding.catalog_loader import (
    ProviderCatalogEntry,
    save_user_catalog_entries,
    user_catalog_path,
)
from tau_coding.credentials import FileCredentialStore, credentials_path
from tau_coding.paths import TauPaths
from tau_coding.provider_catalog import ProviderKind
from tau_coding.provider_config import (
    AnthropicProviderConfig,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER_NAME,
    OpenAICompatibleProviderConfig,
    ProviderConfig,
    ProviderSettings,
    load_provider_settings,
    save_provider_settings,
    upsert_openai_compatible_provider,
    upsert_saved_provider,
)

_KIND_HELP: dict[str, str] = {
    "openai-compatible": "OpenAI / Chat Completions API",
    "anthropic": "Anthropic Messages API",
    "openai-codex": "OpenAI Codex subscription (OAuth)",
    "google-generative-ai": "Google Gemini API",
    "mistral-conversations": "Mistral API",
}

_KIND_DEFAULT_API: dict[str, str] = {
    "openai-compatible": "openai-completions",
    "anthropic": "anthropic-messages",
    "openai-codex": "openai-codex-responses",
    "google-generative-ai": "google-generative-ai",
    "mistral-conversations": "mistral-conversations",
}


def providers_add_command(paths: TauPaths | None = None) -> None:
    """Interactively create or update a custom provider definition."""
    name = typer.prompt("Provider name/id (e.g. nebius)")
    if not name or not name.strip():
        raise typer.BadParameter("Provider name is required.")

    name = name.strip()
    display_name = typer.prompt("Display name", default=name).strip() or name

    kind = _prompt_kind()
    base_url = typer.prompt("Base URL").strip()
    if not base_url:
        raise typer.BadParameter("Base URL is required.")

    default_var = f"{name.upper()}_API_KEY"
    api_key_env = typer.prompt("API key env variable", default=default_var).strip() or default_var

    models_raw = typer.prompt("Model IDs (comma-separated)")
    models = tuple(
        dict.fromkeys(m.strip() for m in models_raw.split(",") if m.strip())
    )
    if not models:
        raise typer.BadParameter("At least one model ID is required.")

    default_model = typer.prompt("Default model", default=models[0]).strip()
    if default_model not in models:
        raise typer.BadParameter(f"Default model must be one of: {', '.join(models)}")

    api_key: str | None = typer.prompt(
        "API key (optional, stored in credential store)", default="", show_default=False
    )
    api_key = api_key.strip() or None

    _save_provider(
        name=name,
        display_name=display_name,
        kind=kind,
        base_url=base_url,
        api_key_env=api_key_env,
        models=models,
        default_model=default_model,
        api_key=api_key,
        paths=paths,
    )

    typer.echo(f"Saved provider '{name}' to {user_catalog_path(paths)}")
    if api_key_env not in __import__("os").environ:
        typer.echo(
            f"Set the {api_key_env} environment variable before using this provider.",
            err=True,
        )


def _prompt_kind() -> str:
    """Prompt the user to select a provider kind."""
    kinds = list(_KIND_HELP.keys())
    typer.echo("Select provider kind:")
    for i, k in enumerate(kinds, 1):
        typer.echo(f"  {i}. {k} — {_KIND_HELP[k]}")
    choice = typer.prompt("Kind", default="1").strip()
    try:
        index = int(choice) - 1
        if 0 <= index < len(kinds):
            return kinds[index]
    except ValueError:
        pass
    if choice in _KIND_HELP:
        return choice
    raise typer.BadParameter(f"Invalid kind. Choose from: {', '.join(kinds)}")


def _save_provider(
    *,
    name: str,
    display_name: str,
    kind: str,
    base_url: str,
    api_key_env: str,
    models: tuple[str, ...],
    default_model: str,
    api_key: str | None,
    paths: TauPaths | None = None,
) -> None:
    """Save a provider definition to the user catalog and credential store."""
    catalog_entry = ProviderCatalogEntry(
        name=name,
        display_name=display_name,
        kind=kind,  # type: ignore[arg-type]
        base_url=base_url.rstrip("/"),
        api_key_env=api_key_env,
        credential_name=name,
        models=models,
        default_model=default_model,
        docs_url=base_url.rstrip("/"),
    )
    save_user_catalog_entries((catalog_entry,), paths=paths)

    if api_key:
        FileCredentialStore(path=credentials_path(paths)).set(name, api_key)

    if kind == "anthropic":
        provider: ProviderConfig = AnthropicProviderConfig(
            name=name,
            base_url=base_url.rstrip("/"),
            api_key_env=api_key_env,
            credential_name=name,
            models=models,
            default_model=default_model,
        )
    elif kind == "openai-codex":
        typer.echo(
            "Note: openai-codex providers cannot be fully configured via CLI. "
            "Use /login in the TUI for OAuth setup.",
            err=True,
        )
        return
    else:
        provider = OpenAICompatibleProviderConfig(
            name=name,
            base_url=base_url.rstrip("/"),
            api_key_env=api_key_env,
            credential_name=name,
            api=_KIND_DEFAULT_API.get(kind, "openai-completions"),
            models=models,
            default_model=default_model,
        )

    upsert_saved_provider(provider, set_default=False, paths=paths)
