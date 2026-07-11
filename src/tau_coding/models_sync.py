"""External model metadata sync from models.dev API.

Fetches model metadata (context windows, reasoning, max tokens) from
https://models.dev/api.json and merges it into the active provider
configuration via ``dataclasses.replace()`` on each ``ProviderConfig``.

Usage::

    from tau_coding.models_sync import sync_models, models_sync_command
"""

from __future__ import annotations

import json
import sys
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
import typer

from tau_coding.provider_config import (
    OpenAICodexProviderConfig,
    ProviderConfig,
    ProviderModelMetadata,
    ProviderSettings,
    load_provider_settings,
    save_provider_settings,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODELS_DEV_URL = "https://models.dev/api.json"
_USER_AGENT = "tau-models-sync/1.0"
_BASE_HEADERS = {"Accept": "application/json", "User-Agent": _USER_AGENT}
REQUEST_TIMEOUT = 15.0

# ---------------------------------------------------------------------------
# Task 1: Provider name mapping
# ---------------------------------------------------------------------------

#: models.dev provider ID → Tau provider.name.
#: Only entries that differ between the two naming systems.
#: When both names match exactly, no mapping is needed.
_PROVIDER_NAME_MAP: dict[str, str] = {
    "x-ai": "xai",
    "z-ai": "zai",
    "opencode-go": "opencode-go",
    "opencode": "opencode-zen",
}


def _resolve_provider_name(
    tau_name: str,
    external_data: dict[str, Any],
) -> str | None:
    """Find the matching key in *external_data* for a Tau provider name.

    Resolution order (3 attempts):
    1. Exact match — *tau_name* is a key in *external_data*
    2. Known mapping — iterate ``_PROVIDER_NAME_MAP`` to find an
       external ID whose mapped value equals *tau_name*
    3. Case-insensitive — compare ``tau_name.lower()`` against all keys

    Returns ``None`` when no match is found.
    """
    # 1. Exact match
    if tau_name in external_data:
        return tau_name

    # 2. Known mapping (reverse lookup)
    for ext_id, mapped_name in _PROVIDER_NAME_MAP.items():
        if mapped_name == tau_name and ext_id in external_data:
            return ext_id

    # 3. Case-insensitive fallback
    tau_lower = tau_name.lower()
    for ext_name in external_data:
        if ext_name.lower() == tau_lower:
            return ext_name

    return None


# ---------------------------------------------------------------------------
# Task 2: Cache I/O utilities
# ---------------------------------------------------------------------------


def _default_cache_path() -> Path:
    """Return the default cache file path (``~/.tau/models/cache.json``)."""
    return Path.home() / ".tau" / "models" / "cache.json"


def _read_cache(path: Path) -> dict[str, Any] | None:
    """Read and validate the cache file at *path*.

    * Missing file → ``None``
    * Corrupt JSON → delete file, print warning, return ``None``
    * Missing ``"data"`` key → delete file, return ``None``
    * Valid → return parsed dict
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print("Warning: Corrupt cache file removed.", file=sys.stderr)
        with suppress(OSError):
            path.unlink()
        return None
    if not isinstance(data, dict) or "data" not in data:
        with suppress(OSError):
            path.unlink()
        return None
    return data


def _write_cache(
    path: Path,
    response: httpx.Response,
    data: dict[str, Any],
) -> None:
    """Write a cache dict to *path* as formatted JSON.

    Captures ``ETag`` and ``Last-Modified`` headers from *response* and
    stores them alongside the raw *data* and an ISO-8601 ``cached_at``
    timestamp.
    """
    etag = response.headers.get("etag")
    last_modified = response.headers.get("last-modified")
    cache: dict[str, Any] = {
        "cached_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),  # noqa: UP017
        "data": data,
    }
    if etag:
        cache["etag"] = etag
    if last_modified:
        cache["last_modified"] = last_modified
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Task 3: Result type and merge logic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SyncResult:
    """Result of a sync operation.

    ``sync_models()`` returns ``(SyncResult, ProviderSettings)`` as a tuple.
    The second element is the (potentially) updated settings and should be
    used only when ``providers_updated > 0`` or ``models_updated > 0``.
    """

    success: bool
    providers_updated: int
    models_updated: int
    source: Literal["api", "cache", "none"]
    error: str | None = None


def _merge_model_data(
    provider: ProviderConfig,
    model_name: str,
    external: dict[str, Any],
    *,
    update_model_metadata: bool,
) -> ProviderConfig:
    """Return a new provider config with external data merged for one model.

    Updates ``context_windows[model_name]`` (always) and, when
    *update_model_metadata* is ``True``, ``model_metadata[model_name]``
    with ``context_window``, ``reasoning``, and ``max_tokens``.

    Returns the **same object** (identity) when no data needs to change
    so callers can detect modifications with ``result is provider``.

    Type validation is applied: ``context`` must be ``int > 0``,
    ``reasoning`` must be ``bool``, ``max_output`` must be ``int > 0``.
    Invalid values are silently skipped.
    """
    changed = False

    # -- Quick return for models not in provider's model list --
    if model_name not in provider.models:
        return provider

    # -- context_windows: updated for all provider types --
    ext_context = (
        external.get("limit", {}).get("context")
        if isinstance(external.get("limit"), dict)
        else None
    )
    new_context_windows = dict(provider.context_windows)
    if (
        ext_context is not None
        and isinstance(ext_context, int)
        and ext_context > 0
        and new_context_windows.get(model_name) != ext_context
    ):
        new_context_windows[model_name] = ext_context
        changed = True

    # -- model_metadata: only for providers that have the field --
    if update_model_metadata:
        ext_reasoning = external.get("reasoning")
        ext_max_output = (
            external.get("limit", {}).get("output")
            if isinstance(external.get("limit"), dict)
            else None
        )

        existing_metadata: dict[str, ProviderModelMetadata] = getattr(
            provider, "model_metadata", {}
        )
        new_model_metadata = dict(existing_metadata)

        md_kwargs: dict[str, Any] = {}
        if ext_context is not None and isinstance(ext_context, int) and ext_context > 0:
            md_kwargs["context_window"] = ext_context
        if ext_reasoning is not None and isinstance(ext_reasoning, bool):
            md_kwargs["reasoning"] = ext_reasoning
        if ext_max_output is not None and isinstance(ext_max_output, int) and ext_max_output > 0:
            md_kwargs["max_tokens"] = ext_max_output

        if md_kwargs:
            if model_name in new_model_metadata:
                base = new_model_metadata[model_name]
                # Only replace when at least one value actually changes
                needs_update = any(getattr(base, k, None) != v for k, v in md_kwargs.items())
                if needs_update:
                    new_model_metadata[model_name] = replace(base, **md_kwargs)
                    changed = True
            else:
                new_model_metadata[model_name] = ProviderModelMetadata(
                    name=model_name,
                    context_window=md_kwargs.get("context_window"),
                    reasoning=md_kwargs.get("reasoning"),
                    max_tokens=md_kwargs.get("max_tokens"),
                )
                changed = True

    if not changed:
        return provider  # identity → caller detects no change

    replace_kwargs: dict[str, Any] = {"context_windows": new_context_windows}
    if update_model_metadata:
        replace_kwargs["model_metadata"] = new_model_metadata

    return replace(provider, **replace_kwargs)


def _merge_external_data(
    settings: ProviderSettings,
    external_data: dict[str, Any],
    *,
    source: Literal["api", "cache"] = "api",
) -> tuple[SyncResult, ProviderSettings]:
    """Iterate *settings.providers*, merge external data per-model.

    Does **not** save settings — returns updated in-memory settings for
    the caller to persist.

    Counts ``providers_updated`` (providers with ≥1 changed model) and
    ``models_updated`` (individual model merges).
    """
    providers_updated = 0
    models_updated = 0
    updated_providers: list[ProviderConfig] = []

    for provider in settings.providers:
        # Resolve provider name in external data
        ext_provider_name = _resolve_provider_name(provider.name, external_data)
        if ext_provider_name is None:
            updated_providers.append(provider)
            continue

        ext_provider = external_data[ext_provider_name]
        if not isinstance(ext_provider, dict):
            updated_providers.append(provider)
            continue

        # OpenAICodexProviderConfig has no model_metadata field
        has_model_metadata = not isinstance(provider, OpenAICodexProviderConfig)

        provider_models_updated = 0
        current: ProviderConfig = provider

        for model_name in provider.models:
            ext_models = ext_provider.get("models", {})
            if not isinstance(ext_models, dict):
                ext_models = {}
            ext_model = ext_models.get(model_name)
            if not isinstance(ext_model, dict):
                continue

            merged = _merge_model_data(
                current,
                model_name,
                ext_model,
                update_model_metadata=has_model_metadata,
            )
            if merged is not current:
                current = merged
                provider_models_updated += 1

        updated_providers.append(current)
        if provider_models_updated > 0:
            providers_updated += 1
        models_updated += provider_models_updated

    if providers_updated == 0 and models_updated == 0:
        return SyncResult(True, 0, 0, source), settings

    new_settings = replace(settings, providers=tuple(updated_providers))
    return (
        SyncResult(
            success=True,
            providers_updated=providers_updated,
            models_updated=models_updated,
            source=source,
        ),
        new_settings,
    )


# ---------------------------------------------------------------------------
# Task 4/5: sync_models coordinator
# ---------------------------------------------------------------------------


def _sync_from_cache(
    settings: ProviderSettings,
    cached: dict[str, Any],
    cache_path: Path,
    *,
    reason: str = "No network",
) -> tuple[SyncResult, ProviderSettings]:
    """Run the merge using cached data, printing a warning to stderr.

    *cached* is the full cache dict (with ``etag``, ``cached_at``,
    ``data`` keys).
    """
    cached_at = cached.get("cached_at", "(unknown date)")
    typer.echo(
        f"Warning: {reason} — using cached data from {cached_at}.",
        err=True,
    )

    cached_data = cached.get("data", {})
    if not isinstance(cached_data, dict):
        return (
            SyncResult(False, 0, 0, "cache", "Cached data is not valid (expected dict)"),
            settings,
        )

    _, new_settings = _merge_external_data(settings, cached_data, source="cache")
    # Re-read the result to get the correct source
    # (the internal _merge_external_data will have source="cache")
    return (
        SyncResult(
            success=True,
            providers_updated=_.providers_updated,
            models_updated=_.models_updated,
            source="cache",
            error=_.error,
        ),
        new_settings,
    )


def sync_models(
    settings: ProviderSettings,
    *,
    http_client: httpx.Client | None = None,
    cache_path: Path | None = None,
) -> tuple[SyncResult, ProviderSettings]:
    """Fetch models.dev API, merge external metadata into *settings*.

    Handles:
    * Conditional GET with ``ETag`` / ``Last-Modified``
    * ``304 Not Modified`` → result with 0 changes, ``source="api"``
    * Network / parse errors → cache fallback (when available)
    * No cache + network error → failure

    Returns ``(SyncResult, updated_settings)``.  Callers should persist
    ``updated_settings`` only when ``result.providers_updated > 0``.
    """
    resolved_cache = cache_path or _default_cache_path()
    close_http = False
    if http_client is None:
        http_client = httpx.Client()
        close_http = True

    try:
        cached = _read_cache(resolved_cache)

        if cached is not None:
            # -- Conditional path: cache exists --
            etag = cached.get("etag")
            last_modified = cached.get("last_modified")
            headers = dict(_BASE_HEADERS)
            if etag:
                headers["If-None-Match"] = etag
            if last_modified:
                headers["If-Modified-Since"] = last_modified

            try:
                resp = http_client.get(MODELS_DEV_URL, headers=headers, timeout=REQUEST_TIMEOUT)
            except httpx.HTTPError as exc:
                return _sync_from_cache(settings, cached, resolved_cache, reason=str(exc))

            if resp.status_code == 304:
                cached_data = cached.get("data", {})
                if isinstance(cached_data, dict):
                    return _merge_external_data(settings, cached_data, source="api")
                return SyncResult(True, 0, 0, "api"), settings

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except json.JSONDecodeError as exc:
                    return _sync_from_cache(
                        settings,
                        cached,
                        resolved_cache,
                        reason=f"Parse error: {exc}",
                    )
                _write_cache(resolved_cache, resp, data)
                return _merge_external_data(settings, data)

            # Non-200/304 status — cache fallback
            return _sync_from_cache(
                settings, cached, resolved_cache, reason=f"HTTP {resp.status_code}"
            )

        # -- Unconditional path: no cache --
        try:
            resp = http_client.get(MODELS_DEV_URL, headers=_BASE_HEADERS, timeout=REQUEST_TIMEOUT)
        except httpx.HTTPError as exc:
            return SyncResult(False, 0, 0, "none", str(exc)), settings

        if resp.status_code == 200:
            try:
                data = resp.json()
            except json.JSONDecodeError as exc:
                return (
                    SyncResult(
                        False,
                        0,
                        0,
                        "none",
                        f"Failed to parse models.dev response: {exc}",
                    ),
                    settings,
                )
            _write_cache(resolved_cache, resp, data)
            return _merge_external_data(settings, data)

        return (
            SyncResult(False, 0, 0, "none", f"Unexpected HTTP {resp.status_code}"),
            settings,
        )
    finally:
        if close_http:
            http_client.close()


# ---------------------------------------------------------------------------
# Task 6: CLI entry point
# ---------------------------------------------------------------------------


def models_sync_command() -> None:
    """CLI entry point: load settings, sync, print summary, save if changed.

    Error messages go to stderr.  Summary goes to stdout.
    Exits with code 1 on hard failure (no cache, no network).
    """
    settings = load_provider_settings()
    cache_path = _default_cache_path()

    with httpx.Client() as client:
        result, updated_settings = sync_models(
            settings,
            http_client=client,
            cache_path=cache_path,
        )

    if result.success:
        # 304 Not Modified — just "Already up to date."
        if result.source == "api" and result.providers_updated == 0 and result.models_updated == 0:
            typer.echo("Already up to date.")
            return

        # Save if there were changes
        if result.providers_updated > 0 or result.models_updated > 0:
            save_provider_settings(updated_settings)

        typer.echo(f"Updated {result.providers_updated} providers ({result.models_updated} models)")
        return

    # Hard failure
    error_msg = result.error or "Unknown error"
    typer.echo(f"Error: {error_msg}", err=True)
    raise typer.Exit(code=1)
