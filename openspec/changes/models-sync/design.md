# Design: Models Sync — External Model Metadata Overlay

**Change**: `models-sync`
**Phase**: design
**Date**: 2026-07-08
**Author**: SDD design phase
**Status**: Draft

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Data Structures](#2-data-structures)
3. [Function Designs and Data Flow](#3-function-designs-and-data-flow)
4. [Provider Name Mapping](#4-provider-name-mapping)
5. [CLI Integration](#5-cli-integration)
6. [Cache Layer](#6-cache-layer)
7. [Error Handling Matrix](#7-error-handling-matrix)
8. [File Changes](#8-file-changes)
9. [Testing Design](#9-testing-design)
10. [Rollout and Rollback](#10-rollout-and-rollback)

---

## 1. Architecture Overview

```
User runs "tau models sync"
         │
         ▼
  cli.py: main()            ──►  models_sync_command() in models_sync.py
  ─ positional_args check        │
  ─ import + call                 │
                                  ├─ load_provider_settings()
                                  │
                                  ├─ sync_models(settings, ...)
                                  │     │
                                  │     ├─ Try cache (ETag conditional)
                                  │     ├─ If miss/fresh: fetch models.dev/api.json
                                  │     ├─ Parse response
                                  │     ├─ For each provider in settings.providers:
                                  │     │     ├─ Resolve provider name match
                                  │     │     ├─ For each model in provider.models:
                                  │     │     │     ├─ Look up external data
                                  │     │     │     ├─ If found → _merge_model_data()
                                  │     │     └─ Replace provider in tuple
                                  │     └─ Return SyncResult
                                  │
                                  ├─ On success with changes → save_provider_settings()
                                  ├─ Print summary
                                  └─ On failure → print error, exit code 1
```

### Merge Point

Merge happens at the **`ProviderSettings` level** (in-memory). `sync_models()` receives the settings, iterates providers, calls `dataclasses.replace()` on each provider config when external data is found, and returns the updated `ProviderSettings` (via `dataclasses.replace(settings, providers=...)`). The caller (`models_sync_command()`) saves if there were changes.

Only **3 fields** per model are touched:
- `context_windows[model_name]` ← external `context`
- `model_metadata[model_name].context_window` ← external `context`
- `model_metadata[model_name].reasoning` ← external `reasoning`
- `model_metadata[model_name].max_tokens` ← external `max_output`

External data **always wins** for these 3 fields. Missing external fields leave static values intact.

---

## 2. Data Structures

All defined in `src/tau_coding/models_sync.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx

from tau_coding.provider_config import (
    OpenAICodexProviderConfig,
    ProviderConfig,
    ProviderModelMetadata,
    ProviderSettings,
    dataclasses_replace as replace,  # actually from dataclasses import replace
)


@dataclass(frozen=True)
class SyncResult:
    """Result of a sync operation."""
    success: bool
    providers_updated: int
    models_updated: int
    source: Literal["api", "cache", "none"]
    error: str | None = None


@dataclass(frozen=True)
class ExternalModelData:
    """Parsed external metadata for one model (safe subset of the API response)."""
    context_window: int | None = None
    reasoning: bool | None = None
    max_tokens: int | None = None
```

### Key observation: `ExternalModelData` is frozen and safe for internal use. The actual API response is parsed defensively — missing or invalid fields produce `None`, which means "keep static value."

### Cache schema (stored as JSON dict, not a dataclass):

```python
# Structure of cache file at ~/.tau/models/cache.json
cache_schema = {
    "etag": str | None,          # ETag header value, quoted as received
    "last_modified": str | None, # Last-Modified header value
    "cached_at": str,            # ISO 8601 timestamp of write time
    "data": dict,                # Raw API response JSON: {provider: {model: {...}}}
}
```

---

## 3. Function Designs and Data Flow

### 3.1 `sync_models()` — Orchestrator

```python
def sync_models(
    settings: ProviderSettings,
    *,
    http_client: httpx.Client | None = None,
    cache_path: Path | None = None,
) -> SyncResult:
    """Fetch models.dev API, merge metadata into provider settings, return summary.
    
    Steps:
    1. Resolve cache_path default: ~/.tau/models/cache.json
    2. Try _read_cache() — returns None if missing/corrupt
    3. If cache has etag: make conditional GET (If-None-Match, If-Modified-Since)
    4. On 304: use cached data, report "Already up to date." (no merge, return 0 changes)
    5. On 200: parse response body, _write_cache(), merge
    6. On network error: fall back to cached data if available
    7. Parse error: fall back to cached data if available
    8. Merge: iterate providers, _resolve_provider_name, then per-model _merge_model_data
    9. Return SyncResult with counts
    """
```

**Detailed flow:**

```
sync_models(settings, http_client=None, cache_path=None):
  │
  ├─ cache_path = cache_path or _default_cache_path()
  │
  ├─ cached = _read_cache(cache_path)       # dict | None
  │
  ├─ if cached and "data" in cached:
  │     etag = cached.get("etag")
  │     last_modified = cached.get("last_modified")
  │     headers = build_conditional_headers(etag, last_modified)
  │     try:
  │         response = http_client.get(url, headers=headers, timeout=15)
  │     except httpx.HTTPError as exc:
  │         # Network error → use cache
  │         return _sync_from_cache(cached["data"], settings, cache_path)
  │
  │     if response.status_code == 304:
  │         # No changes on server
  │         return SyncResult(True, 0, 0, "api")
  │     elif response.status_code == 200:
  │         try:
  │             data = response.json()
  │         except json.JSONDecodeError as exc:
  │             # Parse error → use cache if available
  │             if cached:
  │                 return _sync_from_cache(cached["data"], settings, cache_path)
  │             return SyncResult(False, 0, 0, "none", str(exc))
  │
  │         # Success: write cache, merge
  │         _write_cache(cache_path, response, data)
  │         return _merge_external_data(settings, data)
  │     else:
  │         # Non-200/304 status → use cache if available
  │         if cached:
  │             return _sync_from_cache(cached["data"], settings, cache_path)
  │         return SyncResult(False, 0, 0, "none",
  │                           f"Unexpected HTTP {response.status_code}")
  │
  ├─ else:  # No cache
  │     try:
  │         response = http_client.get(url, headers=base_headers, timeout=15)
  │     except httpx.HTTPError as exc:
  │         return SyncResult(False, 0, 0, "none", str(exc))
  │
  │     if response.status_code == 200:
  │         try:
  │             data = response.json()
  │         except json.JSONDecodeError as exc:
  │             return SyncResult(False, 0, 0, "none", str(exc))
  │         _write_cache(cache_path, response, data)
  │         return _merge_external_data(settings, data)
  │     else:
  │         return SyncResult(False, 0, 0, "none",
  │                           f"Unexpected HTTP {response.status_code}")
```

### 3.2 `_merge_external_data()` — Core Merge Logic

```python
def _merge_external_data(
    settings: ProviderSettings,
    external_data: dict[str, Any],   # {provider_name: {model_name: {field: value}}}
) -> SyncResult:
    """Iterate providers, merge external data, return updated settings + counts."""
    providers_updated = 0
    models_updated = 0
    updated_providers: list[ProviderConfig] = []
    
    for provider in settings.providers:
        # Resolve provider name
        ext_provider_name = _resolve_provider_name(provider.name, external_data)
        if ext_provider_name is None:
            updated_providers.append(provider)
            continue
        
        ext_provider = external_data[ext_provider_name]
        if not isinstance(ext_provider, dict):
            updated_providers.append(provider)
            continue
        
        # Check if provider type has model_metadata
        has_model_metadata = not isinstance(provider, OpenAICodexProviderConfig)
        
        provider_models_updated = 0
        current_provider = provider
        
        for model_name in provider.models:
            ext_model = ext_provider.get(model_name)
            if not isinstance(ext_model, dict):
                continue
            
            # Merge this model
            new_provider = _merge_model_data(
                current_provider, model_name, ext_model,
                update_model_metadata=has_model_metadata,
            )
            if new_provider is not current_provider:
                current_provider = new_provider
                provider_models_updated += 1
        
        updated_providers.append(current_provider)
        if provider_models_updated > 0:
            providers_updated += 1
        models_updated += provider_models_updated
    
    if providers_updated > 0 or models_updated > 0:
        new_settings = replace(
            settings,
            providers=tuple(updated_providers),
        )
        # We need to return updated settings somehow. Options:
        # Option A: mutate SyncResult to carry the settings
        # Option B: return a separate value
        #
        # Decision: Use a frozen dataclass for SyncResult. The caller
        # (models_sync_command) gets the updated settings as a return value.
        # See models_sync_command for the two-return-value pattern.
    
    return SyncResult(
        success=True,
        providers_updated=providers_updated,
        models_updated=models_updated,
        source="api",  # or "cache" when called from _sync_from_cache
    ), new_settings_if_changed
```

**Wait — critical design decision:** `SyncResult` alone can't carry the updated settings. The merge produces a new `ProviderSettings` that the caller needs. Two options:

- **Option A (chosen)**: Return `tuple[SyncResult, ProviderSettings]` from internal merge functions. `sync_models()` returns only `SyncResult` publicly, but passes the updated settings back through `models_sync_command()` via a closure or a mutable holder.

- **Option B**: Move the save logic into `sync_models()`. This violates separation of concerns (sync should not know about saving).

- **Option C (BEST — adopted)**: Have `sync_models()` return a `SyncResult` plus store the updated settings on the result itself. Since `SyncResult` is frozen and changing it to mutable would break the contract, we use a **lightweight mutable holder** pattern: `sync_models` returns `SyncResult`, and `models_sync_command` detects changes by comparing the original settings with what was produced.

**FINAL DECISION**: `_merge_external_data()` returns `(SyncResult, ProviderSettings | None)`. If `providers_updated > 0`, the second element is the new settings. `sync_models()` wraps this: if the caller provided a mutable callback or we use an internal helper, the `models_sync_command()` function calls `_merge_external_data` directly via `sync_models`'s internal path. **Simplest approach**: `sync_models` returns `SyncResult` only, and `models_sync_command` re-loads settings and calls `_merge_external_data` directly. This avoids coupling.

**REFINED ARCHITECTURE**: Split the concern:

- `sync_models()`: public API. Returns `SyncResult`. Handles fetch, cache, parse.
- `models_sync_command()`: CLI entry point. It calls `sync_models` to get the data, then calls a new **internal** `_apply_sync(settings, external_data) -> tuple[SyncResult, ProviderSettings | None]` that does the merge.

**SIMPLEST CORRECT DESIGN**: Let `sync_models` call a private `_merge_and_replace` that returns the new settings, and have `sync_models` return both through a small mutable result object. Actually — the cleanest Python pattern:

```python
@dataclass
class _SyncState:
    """Mutable internal state accumulated during sync."""
    settings: ProviderSettings
    providers_updated: int = 0
    models_updated: int = 0
```

`sync_models` creates `_SyncState(settings=settings)` and passes it through the merge pipeline. At the end, it constructs `SyncResult` from the state's counts and returns the state's settings alongside. But since we want a clean public API...

**FINAL FINAL DECISION**: Just have `sync_models` accept a `settings` argument and return `(SyncResult, ProviderSettings)`. The caller uses the returned settings only if `result.providers_updated > 0`. This is the simplest correct approach.

```python
def sync_models(
    settings: ProviderSettings,
    *,
    http_client: httpx.Client | None = None,
    cache_path: Path | None = None,
) -> tuple[SyncResult, ProviderSettings]:
    """Fetch models.dev API, merge metadata into provider settings.
    
    Returns (result, updated_settings). Caller uses updated_settings only
    when result.providers_updated > 0.
    """
```

### 3.3 `_merge_model_data()` — Single Model Merge

```python
def _merge_model_data(
    provider: ProviderConfig,
    model_name: str,
    external: dict[str, Any],
    *,
    update_model_metadata: bool,
) -> ProviderConfig:
    """Return a new provider config with external data merged for one model.
    
    Merges context_window, reasoning, max_tokens from external into:
      - context_windows[model_name] (always, if 'context' present)
      - model_metadata[model_name] (if provider has model_metadata and 
        entry exists for this model or can be created)
    
    Uses dataclasses.replace() since all ProviderConfig variants are frozen.
    Returns the original provider unchanged if no merge is needed (identity).
    """
    changed = False
    
    # --- context_windows update ---
    ext_context = external.get("context")
    new_context_windows = dict(provider.context_windows)
    if ext_context is not None and isinstance(ext_context, int) and ext_context > 0:
        current = new_context_windows.get(model_name)
        if current != ext_context:
            new_context_windows[model_name] = ext_context
            changed = True
    
    # --- model_metadata update (only for providers that have it) ---
    if update_model_metadata:
        ext_reasoning = external.get("reasoning")
        ext_max_output = external.get("max_output")
        
        existing_metadata = provider.model_metadata  # type: ignore
        new_model_metadata = dict(existing_metadata)
        
        # Build updated metadata only if we have data
        needs_metadata_update = False
        metadata_kwargs: dict[str, Any] = {}
        
        if ext_reasoning is not None and isinstance(ext_reasoning, bool):
            metadata_kwargs["reasoning"] = ext_reasoning
            needs_metadata_update = True
        if ext_max_output is not None and isinstance(ext_max_output, int) and ext_max_output > 0:
            metadata_kwargs["max_tokens"] = ext_max_output
            needs_metadata_update = True
        if ext_context is not None and isinstance(ext_context, int) and ext_context > 0:
            metadata_kwargs["context_window"] = ext_context
            needs_metadata_update = True
        
        if needs_metadata_update:
            if model_name in new_model_metadata:
                # Update existing metadata
                base = new_model_metadata[model_name]
                new_model_metadata[model_name] = replace(
                    base,
                    **metadata_kwargs,
                )
            else:
                # No existing metadata entry for this model — create one
                new_model_metadata[model_name] = ProviderModelMetadata(
                    name=model_name,
                    context_window=metadata_kwargs.get("context_window"),
                    reasoning=metadata_kwargs.get("reasoning"),
                    max_tokens=metadata_kwargs.get("max_tokens"),
                )
            changed = True
    
    if not changed:
        return provider  # Same object identity → caller knows unchanged
    
    # Build the replace kwargs
    replace_kwargs: dict[str, Any] = {
        "context_windows": new_context_windows,
    }
    if update_model_metadata:
        replace_kwargs["model_metadata"] = new_model_metadata
    
    return replace(provider, **replace_kwargs)
```

**Critical detail**: For `OpenAICodexProviderConfig`, `update_model_metadata` is `False`. We only touch `context_windows`.

**Critical detail 2**: When a model exists in `provider.models` but has no entry in `provider.model_metadata`, we **create** a new `ProviderModelMetadata` entry. This is intentional — the sync can add metadata where the static catalog had none.

**Critical detail 3**: We validate types before merging. `ext_context` must be `int` and `> 0`. `ext_reasoning` must be `bool`. `ext_max_output` must be `int` and `> 0`. This prevents corrupt API data from setting weird values.

### 3.4 `_resolve_provider_name()`

```python
_PROVIDER_NAME_MAP: dict[str, str] = {
    # models.dev provider ID → Tau provider.name
    "x-ai": "xai",
    "z-ai": "zai",
    "opencode-go": "opencode-go",
    # Add more as discovered; updates are backward-compatible
}


def _resolve_provider_name(
    tau_name: str,
    external_data: dict[str, Any],
) -> str | None:
    """Find the matching provider name in external_data for a Tau provider name.
    
    Resolution order:
    1. Exact match (fast path)
    2. Known mapping in _PROVIDER_NAME_MAP (models.dev ID → Tau name)
    3. Case-insensitive match against all keys in external_data
    4. Return None if no match
    """
    # 1. Exact match
    if tau_name in external_data:
        return tau_name
    
    # 2. Known mapping (reverse lookup: find models.dev ID that maps to tau_name)
    for ext_id, mapped_name in _PROVIDER_NAME_MAP.items():
        if mapped_name == tau_name and ext_id in external_data:
            return ext_id
    
    # 3. Case-insensitive fallback
    tau_lower = tau_name.lower()
    for ext_name in external_data:
        if ext_name.lower() == tau_lower:
            return ext_name
    
    return None
```

**Design rationale for mapping direction**: The map stores `models.dev ID → Tau name`. The reverse lookup (iterate map to find matching Tau name) is correct because multiple models.dev IDs could map to the same Tau name, and we want to find the right external key. This is O(n) where n = provider count (typically <10), so performance is irrelevant.

### 3.5 `_sync_from_cache()` — Cache Fallback

```python
def _sync_from_cache(
    settings: ProviderSettings,
    cached_data: dict[str, Any],
    cache_path: Path,
) -> tuple[SyncResult, ProviderSettings]:
    """Run the merge using cached data instead of a live API fetch.
    
    Prints a warning to stderr about offline mode.
    Returns (SyncResult with source="cache", updated_settings).
    """
    # Print warning (caller's responsibility in models_sync_command)
    result, new_settings = _merge_external_data(settings, cached_data)
    return (
        SyncResult(
            success=result.success,
            providers_updated=result.providers_updated,
            models_updated=result.models_updated,
            source="cache",
            error=result.error,
        ),
        new_settings,
    )
```

### 3.6 `models_sync_command()` — CLI Entry Point

```python
def models_sync_command() -> None:
    """CLI entry point: load settings, sync, print summary, save if changed."""
    settings = load_provider_settings()
    cache_path = _default_cache_path()
    
    with httpx.Client() as client:
        result, updated_settings = sync_models(
            settings,
            http_client=client,
            cache_path=cache_path,
        )
    
    if result.success and result.source == "api":
        # Came from live API
        if result.providers_updated > 0 or result.models_updated > 0:
            save_provider_settings(updated_settings)
            typer.echo(f"Updated {result.providers_updated} providers ({result.models_updated} models)")
        else:
            # 304 or no merge changes
            if result.models_updated == 0 and result.providers_updated == 0:
                typer.echo("Already up to date.")
            else:
                typer.echo(f"Updated {result.providers_updated} providers ({result.models_updated} models)")
    
    elif result.success and result.source == "cache":
        # Offline fallback — merge from cache
        if result.providers_updated > 0 or result.models_updated > 0:
            save_provider_settings(updated_settings)
        # Print warning + summary
        # Warning printed by _sync_from_cache or models_sync_command
        typer.echo(
            f"Updated {result.providers_updated} providers ({result.models_updated} models)",
            err=True,
        )
    
    elif not result.success and result.source == "none":
        typer.echo(f"Error: {result.error}", err=True)
        raise typer.Exit(code=1)
```

**Wait — I need to refine this.** Looking at the spec scenarios more carefully:

**304**: `result.providers_updated == 0 and result.models_updated == 0`. Print "Already up to date." DO NOT save. Source = "api".

**Cache fallback with merges**: Print warning to stderr, then print sync summary. Save if changes.

**Network error, no cache**: `SyncResult(success=False, source="none")`. Print error to stderr. Exit code 1.

Let me revise the CLI function:

```python
def models_sync_command() -> None:
    """CLI entry point: load settings, sync, print summary, save if changed."""
    settings = load_provider_settings()
    cache_path = _default_cache_path()
    
    with httpx.Client() as client:
        result, updated_settings = sync_models(
            settings,
            http_client=client,
            cache_path=cache_path,
        )
    
    if result.success:
        if result.source == "cache":
            # Offline cache fallback
            typer.echo(
                f"Warning: No network — using cached data.", err=True
            )
        
        if result.providers_updated == 0 and result.models_updated == 0 and result.source == "api":
            # 304 Not Modified
            typer.echo("Already up to date.")
            return
        
        # Save if there were changes
        if result.providers_updated > 0 or result.models_updated > 0:
            save_provider_settings(updated_settings)
        
        typer.echo(f"Updated {result.providers_updated} providers ({result.models_updated} models)")
        
        if not result.success:
            raise typer.Exit(code=1)
    
    else:
        # result.success is False
        typer.echo(f"Error: {result.error}", err=True)
        raise typer.Exit(code=1)
```

Hmm, wait. Looking at the spec's error handling matrix more carefully:

| Failure mode | Behavior |
|---|---|
| **API returns malformed JSON** | Use cache if available, else exit code 1. Error message to stderr. |
| **Network error** | Use cache if available. If no cache, exit code 1 with error message. |

In these cases, `sync_models` will internally try the cache fallback. If cache is available, it returns `SyncResult(success=True, source="cache")` with the merged results. If no cache, it returns `SyncResult(success=False, source="none")`.

So `models_sync_command` doesn't need to worry about parse errors or network errors — `sync_models` handles the fallback and returns the appropriate result.

But what about the "No network — using cached data" warning? It should only print when we're using cache as a fallback from a failed network request, not when we intentionally read cache because the API returned 304.

Let me think about this... The spec says:

- 304: "Already up to date." No cache warning.
- Cache used as network fallback: "Warning: No network — using cached data from {cached_at}." to stderr.

So `sync_models` needs to report WHY it used cache. Options:
1. Add a `fallback_reason` field to SyncResult
2. Print the warning from within sync_models
3. Return different source values

I'll go with option 2 (print warning from within sync_models when falling back to cache due to network error or parse error), since it's the simplest and the warning is an output concern closely tied to the fallback decision.

Actually, better: I'll add an `info` field to SyncResult:

No, that's complicating the data structure. Let's just have `_sync_from_cache` print the warning itself. It's an internal function and the warning is always the same.

**Revised approach**:

```python
def _sync_from_cache(
    settings: ProviderSettings,
    cached_data: dict[str, Any],
    cache_path: Path,
    *,
    reason: str = "No network",
) -> tuple[SyncResult, ProviderSettings]:
    """Run merge from cached data, printing a warning to stderr."""
    cached_at = "(unknown date)"
    # Try to read cached_at from the cache metadata
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        cached_at = raw.get("cached_at", cached_at)
    except Exception:
        pass
    
    typer.echo(
        f"Warning: {reason} — using cached data from {cached_at}.",
        err=True,
    )
    
    # ... merge and return ...
```

Wait, `_sync_from_cache` takes `cached_data` (the parsed data dict) but needs to read `cached_at` from the raw cache file. I should pass the raw cache dict or the cache path instead. Let me refine:

`sync_models` reads the cache once with `_read_cache()`, which returns the full cache dict `{"etag": ..., "last_modified": ..., "cached_at": ..., "data": {...}}` or `None`. Then it passes `cached_dict["data"]` (the raw API data) to `_merge_external_data`. The `cached_at` metadata is already available from the initial read.

Better: pass `cached_at` as a parameter.

Let me finalize the function designs in the actual document. I think I have enough detail to write it now. Let me produce the final document.

For the `models_sync_command` flow more carefully matching the spec:

```
models_sync_command():
  1. Load settings
  2. Call sync_models()
  3. Result handling:

     success=True, source="api", providers=0, models=0
       → "Already up to date." (304 scenario)
     
     success=True, source="api", providers>0 or models>0
       → save_provider_settings(), print "Updated N providers (M models)"
     
     success=True, source="cache"
       → warning already printed by sync_models
       → if providers>0 or models>0: save_provider_settings()
       → print "Updated N providers (M models)"
     
     success=False, source="none"
       → print error to stderr, exit code 1
```

Now let me write the full design document.<｜end▁of▁thinking｜>

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="write">
<｜｜DSML｜｜parameter name="content" string="true"># Design: Models Sync — External Model Metadata Overlay

**Change**: `models-sync`
**Phase**: design
**Date**: 2026-07-08
**Author**: SDD design phase
**Status**: Draft

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Data Structures](#2-data-structures)
3. [Function Designs and Data Flow](#3-function-designs-and-data-flow)
4. [Provider Name Mapping](#4-provider-name-mapping)
5. [CLI Integration](#5-cli-integration)
6. [Cache Layer](#6-cache-layer)
7. [Error Handling Matrix](#7-error-handling-matrix)
8. [File Changes](#8-file-changes)
9. [Testing Design](#9-testing-design)
10. [Rollout and Rollback](#10-rollout-and-rollback)

---

## 1. Architecture Overview

```
User runs "tau models sync"
         │
         ▼
  cli.py: main()            ──►  models_sync_command() in models_sync.py
  ─ positional_args check        │
  ─ import + call                 │
                                  ├─ load_provider_settings()
                                  │
                                  ├─ sync_models(settings, ...)
                                  │     │
                                  │     ├─ Try _read_cache (ETag conditional)
                                  │     ├─ If cache hit with ETag: conditional GET
                                  │     │   - 304 → return (0 changes, source="api")
                                  │     │   - 200 → parse, _write_cache, merge
                                  │     │   - error → _sync_from_cache
                                  │     ├─ If cache miss: unconditional GET
                                  │     │   - 200 → parse, _write_cache, merge
                                  │     │   - error → return (failure)
                                  │     └─ Return (SyncResult, updated_settings)
                                  │
                                  ├─ On success with changes → save_provider_settings()
                                  ├─ Print summary
                                  └─ On failure → print error, exit code 1
```

### Merge Point

Merge happens at the **`ProviderSettings` level** (in-memory). `sync_models()` receives the settings, iterates providers, calls `dataclasses.replace()` on each provider config when external data is found, and returns the updated `ProviderSettings`. The caller (`models_sync_command()`) saves if there were changes.

Only **3 fields** per model are touched:

| Field | External source | Effect |
|-------|----------------|--------|
| `context_windows[model_name]` | `context` | Updated directly on provider |
| `model_metadata[model_name].context_window` | `context` | Updated via `replace()` |
| `model_metadata[model_name].reasoning` | `reasoning` | Updated via `replace()` |
| `model_metadata[model_name].max_tokens` | `max_output` | Updated via `replace()` |

External data **always wins** for these 3 fields. Missing/invalid external fields leave static values intact.

### No changes to existing modules

- `provider_config.py` → NO changes to types, merge logic, or `_merge_provider_model_metadata`
- `catalog_loader.py` → NO changes
- `session.py` → NO changes (context_window_tokens already reads `provider.context_windows`)
- `provider_catalog.py` → NO changes

The only modified existing file is `cli.py` (~12 lines for import + command handler).

---

## 2. Data Structures

All defined in `src/tau_coding/models_sync.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx

from tau_coding.provider_config import (
    OpenAICodexProviderConfig,
    ProviderConfig,
    ProviderModelMetadata,
    ProviderSettings,
    load_provider_settings,
    save_provider_settings,
)


@dataclass(frozen=True)
class SyncResult:
    """Result of a sync operation.
    
    Note: sync_models() returns (SyncResult, ProviderSettings) as a tuple.
    The second element is the (potentially) updated settings. Only use it
    when providers_updated > 0 or models_updated > 0.
    """
    success: bool
    providers_updated: int
    models_updated: int
    source: Literal["api", "cache", "none"]
    error: str | None = None
```

### Why `SyncResult` is frozen

Follows the existing `dataclass(frozen=True)` pattern used throughout `provider_config.py` (`ProviderSettings`, `ProviderConfig` variants, etc.). Immutability prevents accidental mutation and makes the result safe to pass around.

### Why return `(SyncResult, ProviderSettings)` instead of mutating SyncResult

The merge produces a new `ProviderSettings` (immutable, via `replace()`). The caller needs access to it for saving. Since `SyncResult` is frozen, we return a tuple.

---

## 3. Function Designs and Data Flow

### 3.1 `sync_models()` — Public API Orchestrator

```python
MODELS_DEV_URL = "https://models.dev/api.json"
DEFAULT_CACHE_DIR = "~/.tau/models"
CACHE_FILENAME = "cache.json"
REQUEST_TIMEOUT = 15.0

_USER_AGENT = "tau-models-sync/1.0"

_BASE_HEADERS = {
    "Accept": "application/json",
    "User-Agent": _USER_AGENT,
}


def _default_cache_path() -> Path:
    return (Path.home() / ".tau" / "models" / "cache.json").expanduser()


def sync_models(
    settings: ProviderSettings,
    *,
    http_client: httpx.Client | None = None,
    cache_path: Path | None = None,
) -> tuple[SyncResult, ProviderSettings]:
    """Fetch models.dev API, merge metadata into provider settings.

    Returns (SyncResult, updated_settings). Caller should save
    updated_settings only when result.providers_updated > 0.

    Handles:
    - Conditional GET with ETag/Last-Modified
    - 304 → no changes
    - Network errors → cache fallback
    - Parse errors → cache fallback
    - No cache + network error → failure
    """
```

#### Detailed flow:

```
sync_models(settings, http_client, cache_path):
  │
  ├─ cache_path = cache_path or _default_cache_path()
  ├─ close_http = False
  ├─ if http_client is None:
  │     http_client = httpx.Client()
  │     close_http = True
  │
  ├─ cached = _read_cache(cache_path)    # dict | None
  │
  ├─ if cached is not None:              ──┐
  │     etag = cached.get("etag")          │ Conditional path
  │     last_modified = cached.get("last_modified")
  │     headers = dict(_BASE_HEADERS)
  │     if etag:                           │ 
  │         headers["If-None-Match"] = etag
  │     if last_modified:
  │         headers["If-Modified-Since"] = last_modified
  │     try:
  │         resp = http_client.get(MODELS_DEV_URL, headers=headers,
  │                                timeout=REQUEST_TIMEOUT)
  │     except httpx.HTTPError as exc:
  │         # Network error → use cache
  │         return _sync_from_cache(settings, cached, cache_path,
  │                                 reason=str(exc))
  │
  │     if resp.status_code == 304:
  │         return (SyncResult(success=True, providers_updated=0,
  │                            models_updated=0, source="api"),
  │                 settings)
  │
  │     if resp.status_code == 200:
  │         try:
  │             data = resp.json()
  │         except json.JSONDecodeError as exc:
  │             return _sync_from_cache(settings, cached, cache_path,
  │                                     reason=f"Parse error: {exc}")
  │         _write_cache(cache_path, resp, data)
  │         return _merge_external_data(settings, data)
  │
  │     # Non-200/304 from server
  │     return _sync_from_cache(settings, cached, cache_path,
  │                             reason=f"HTTP {resp.status_code}")
  │
  ├─ else:                                 ──┐
  │     # No cache — direct fetch            │ Unconditional path
  │     try:
  │         resp = http_client.get(MODELS_DEV_URL, headers=_BASE_HEADERS,
  │                                timeout=REQUEST_TIMEOUT)
  │     except httpx.HTTPError as exc:
  │         return (SyncResult(False, 0, 0, "none", str(exc)), settings)
  │
  │     if resp.status_code == 200:
  │         try:
  │             data = resp.json()
  │         except json.JSONDecodeError as exc:
  │             return (SyncResult(False, 0, 0, "none",
  │                               f"Failed to parse models.dev response: {exc}"),
  │                       settings)
  │         _write_cache(cache_path, resp, data)
  │         return _merge_external_data(settings, data)
  │
  │     return (SyncResult(False, 0, 0, "none",
  │                        f"Unexpected HTTP {resp.status_code}"), settings)
  │
  └─ if close_http:
         http_client.close()
```

**Key design decisions:**

- HTTP client lifecycle: If the caller provides one, we don't close it (dependency injection friendly for tests). If none provided, we create and close.
- 304 returns the **original** settings unchanged — no unnecessary `replace()` calls.
- Parse error message includes the specific error from `json.JSONDecodeError`.

### 3.2 `_merge_external_data()` — Core Merge Logic

```python
def _merge_external_data(
    settings: ProviderSettings,
    external_data: dict[str, Any],   # {provider_name: {model_name: {field: value}}}
) -> tuple[SyncResult, ProviderSettings]:
    """Iterate providers, merge external data per-model.
    
    Does NOT save settings — only returns updated in-memory settings.
    The caller decides whether to persist.
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
        current = provider

        for model_name in provider.models:
            ext_model = ext_provider.get(model_name)
            if not isinstance(ext_model, dict):
                continue

            merged = _merge_model_data(
                current, model_name, ext_model,
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
        return (
            SyncResult(True, 0, 0, "api"),
            settings,
        )

    new_settings = replace(settings, providers=tuple(updated_providers))
    return (
        SyncResult(
            success=True,
            providers_updated=providers_updated,
            models_updated=models_updated,
            source="api",
        ),
        new_settings,
    )
```

**Key design decisions:**

- Source is hardcoded to `"api"` here. When called from `_sync_from_cache`, the caller overrides the source to `"cache"`.
- **Provider skipped entirely** when not found in external data → `providers_updated` not incremented, no changes.
- **Model skipped** when not in external provider's model list → `models_updated` not incremented.
- Uses identity check (`merged is not current`) to detect whether `_merge_model_data` actually made changes. `_merge_model_data` returns the original object unchanged when nothing needs merging.

### 3.3 `_merge_model_data()` — Single Model Merge

```python
def _merge_model_data(
    provider: ProviderConfig,
    model_name: str,
    external: dict[str, Any],
    *,
    update_model_metadata: bool,
) -> ProviderConfig:
    """Return a new provider config with external data merged for one model.
    
    Returns the original provider unchanged (same identity) if no data
    needs to be merged — lets callers detect changes via identity check.
    """
    changed = False

    # ── context_windows: always updated for all provider types ──
    ext_context = external.get("context")
    new_context_windows = dict(provider.context_windows)
    if ext_context is not None and isinstance(ext_context, int) and ext_context > 0:
        if new_context_windows.get(model_name) != ext_context:
            new_context_windows[model_name] = ext_context
            changed = True

    # ── model_metadata: only for providers that have the field ──
    if update_model_metadata:
        ext_reasoning = external.get("reasoning")
        ext_max_output = external.get("max_output")

        existing_metadata: dict[str, ProviderModelMetadata] = provider.model_metadata  # type: ignore[attr-defined]
        new_model_metadata = dict(existing_metadata)

        md_kwargs: dict[str, Any] = {}
        if ext_reasoning is not None and isinstance(ext_reasoning, bool):
            md_kwargs["reasoning"] = ext_reasoning
        if ext_max_output is not None and isinstance(ext_max_output, int) and ext_max_output > 0:
            md_kwargs["max_tokens"] = ext_max_output
        if ext_context is not None and isinstance(ext_context, int) and ext_context > 0:
            md_kwargs["context_window"] = ext_context

        if md_kwargs:
            if model_name in new_model_metadata:
                base = new_model_metadata[model_name]
                new_model_metadata[model_name] = replace(base, **md_kwargs)
            else:
                # Create metadata entry where none existed
                new_model_metadata[model_name] = ProviderModelMetadata(
                    name=model_name,
                    context_window=md_kwargs.get("context_window"),
                    reasoning=md_kwargs.get("reasoning"),
                    max_tokens=md_kwargs.get("max_tokens"),
                )
            changed = True

    if not changed:
        return provider  # Same identity → caller detects no change

    replace_kwargs: dict[str, Any] = {"context_windows": new_context_windows}
    if update_model_metadata:
        replace_kwargs["model_metadata"] = new_model_metadata

    return replace(provider, **replace_kwargs)
```

**Key design decisions:**

- **Type validation**: `ext_context` must be `int and > 0`; `ext_reasoning` must be `bool`; `ext_max_output` must be `int and > 0`. Invalid types/values are silently skipped.
- **New metadata creation**: If a model is in `provider.models` but has no existing `model_metadata` entry, we **create** one. This lets the sync add metadata where the static catalog was missing it.
- **Identity-based change detection**: Returns same object when nothing changed (`return provider`). Caller checks `merged is not current`.
- `# type: ignore[attr-defined]` for `provider.model_metadata`: Since `ProviderConfig` is a union type and `OpenAICodexProviderConfig` doesn't have `model_metadata`, mypy flags it. The `update_model_metadata` guard ensures this path is never reached for codex providers.

### 3.4 `_sync_from_cache()` — Offline/Cache Fallback

```python
def _sync_from_cache(
    settings: ProviderSettings,
    cached: dict[str, Any],     # Full cache dict: {etag, last_modified, cached_at, data}
    cache_path: Path,
    *,
    reason: str = "No network",
) -> tuple[SyncResult, ProviderSettings]:
    """Merge from cached data when live fetch fails.
    
    Prints a warning to stderr with the cached_at timestamp.
    Returns SyncResult with source="cache".
    """
    cached_at = cached.get("cached_at", "(unknown date)")
    typer.echo(
        f"Warning: {reason} — using cached data from {cached_at}.",
        err=True,
    )

    cached_data = cached.get("data", {})
    if not isinstance(cached_data, dict):
        return (
            SyncResult(False, 0, 0, "cache",
                       "Cached data is not valid (expected dict)"),
            settings,
        )

    result, new_settings = _merge_external_data(settings, cached_data)
    return (
        SyncResult(
            success=result.success,
            providers_updated=result.providers_updated,
            models_updated=result.models_updated,
            source="cache",
            error=result.error,
        ),
        new_settings,
    )
```

### 3.5 `models_sync_command()` — CLI Entry Point

```python
def models_sync_command() -> None:
    """CLI entry point: load settings, sync, print summary, save if changed.
    
    Error messages go to stderr. Summary goes to stdout.
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
        if result.source == "cache":
            # Warning already printed inside _sync_from_cache
            pass

        if result.providers_updated == 0 and result.models_updated == 0:
            if result.source == "api":
                # 304 Not Modified or no merge changes from API
                typer.echo("Already up to date.")
            # For cache source with 0 changes: still print the zero summary
            # (spec says "Updated 0 providers (0 models)" for that case)
        
        if result.providers_updated > 0 or result.models_updated > 0:
            save_provider_settings(updated_settings)

        typer.echo(
            f"Updated {result.providers_updated} providers "
            f"({result.models_updated} models)"
        )
        return

    # Not successful — hard failure
    error_msg = result.error or "Unknown error"
    typer.echo(f"Error: {error_msg}", err=True)
    raise typer.Exit(code=1)
```

**Scenarios mapped:**

| Scenario | `result` | Behavior |
|----------|----------|----------|
| First sync, API returns data | `(True, N, M, "api")` with N>0 or M>0 | Save, print "Updated N providers (M models)" |
| 304 Not Modified | `(True, 0, 0, "api")` | Print "Already up to date." No save |
| Cache fallback with merges | `(True, N, M, "cache")` | Warning printed. Save if >0. Print summary |
| Cache fallback, no changes | `(True, 0, 0, "cache")` | Warning printed. Print "Updated 0 providers (0 models)" |
| Network error, no cache | `(False, 0, 0, "none", err)` | Print error to stderr, exit code 1 |
| Parse error, no cache | `(False, 0, 0, "none", err)` | Print error to stderr, exit code 1 |

**Corner case**: "Updated 0 providers (0 models)" is printed for both the API-304 case ("Already up to date." is also printed, but... wait — the spec says 304 should print only "Already up to date." and nothing else, while the cache-fallback-with-zero-changes should print the summary. Let me re-check:

- Spec scenario "Subsequent sync with no changes (304)": prints "Already up to date." — no summary.
- Spec scenario "Offline fallback with cache": returns merged results (which may be >0 changes or 0). If 0, still prints "Updated 0 providers (0 models)"? Actually the spec says "prints a sync summary". Let me assume 0-changes case from cache also prints the summary. But 304 does NOT print the summary — just "Already up to date."

So I need to distinguish between "API said 304" (no summary, just "Already up to date") and "cache merge produced 0 changes" (print summary with zeroes).

How? When the API returns 304, we return `(result with 0/0, original settings)`. When the cache merge produces 0 changes, we also return `(result with 0/0, original settings)`. But the source is different: "api" for 304, "cache" for cache fallback.

Fix: Only print "Already up to date." when `result.source == "api"` AND `providers_updated == 0` AND `models_updated == 0`. Always print the summary line regardless (spec wants "Updated 0 providers (0 models)" even from cache with no changes).

Wait, looking at spec again for 304 scenario: "THEN the system prints `"Already up to date."` AND no settings are modified AND the cache file's `cached_at` timestamp is NOT updated."

And for cache fallback: "THEN the system prints `"Warning: No network — using cached data from {cached_at}."` to stderr AND the system merges metadata from the cache file AND the system prints a sync summary."

So for 304: JUST "Already up to date." (no summary, no warning).
For cache fallback: warning (already printed) + sync summary.
For API with changes: just the summary.

The simplest way:
```python
if result.source == "api" and result.providers_updated == 0 and result.models_updated == 0:
    typer.echo("Already up to date.")
    return

# For all other success cases: print summary
if result.providers_updated > 0 or result.models_updated > 0:
    save_provider_settings(updated_settings)
typer.echo(f"Updated {result.providers_updated} providers ({result.models_updated} models)")
```

This matches all scenarios. ✅

---

## 4. Provider Name Mapping

```python
# models.dev provider ID → Tau provider.name
# Only entries that differ between the two naming systems.
# When both names match exactly, no mapping is needed.
_PROVIDER_NAME_MAP: dict[str, str] = {
    "x-ai": "xai",
    "z-ai": "zai",
    "opencode-go": "opencode-go",
    # Add more as discovered — backward compatible additions only
}


def _resolve_provider_name(
    tau_name: str,
    external_data: dict[str, Any],
) -> str | None:
    """Find the matching key in external_data for a Tau provider name.
    
    Resolution order (3 attempts, O(n) at each, n < 10 providers):
    1. Exact match: tau_name in external_data
    2. Known mapping: iterate _PROVIDER_NAME_MAP to find ext_id → tau_name
    3. Case-insensitive: find any key in external_data matching tau_name.lower()
    
    Returns None when no match is found.
    """
    # 1. Exact match
    if tau_name in external_data:
        return tau_name

    # 2. Known mapping (reverse: find models.dev ID that maps to tau_name)
    for ext_id, mapped_name in _PROVIDER_NAME_MAP.items():
        if mapped_name == tau_name and ext_id in external_data:
            return ext_id

    # 3. Case-insensitive fallback
    tau_lower = tau_name.lower()
    for ext_name in external_data:
        if ext_name.lower() == tau_lower:
            return ext_name

    return None
```

**Why reverse lookup?** The map goes `models.dev ID → Tau name`. A Tau provider named `"xai"` needs to find the key `"x-ai"` in the external data. We iterate the map and check if any mapped value matches `tau_name`. Simple, correct, performance irrelevant (n < 10).

---

## 5. CLI Integration

### Import in `cli.py`

```python
# Add after: from tau_coding.provider_add import providers_add_command
from tau_coding.models_sync import models_sync_command
```

### Handler in `main()`

```python
# Add after the `providers` block (line ~276), before the `setup` block:

if prompt_option is None and command == "models":
    if len(positional_args) >= 2 and positional_args[1] == "sync":
        models_sync_command()
        raise typer.Exit()
```

### Why NOT `tau models` with no arguments (TUI fallthrough)?

Following the spec: `tau models` (no subcommand) falls through to the TUI, treating `"models"` as a prompt. Only `tau models sync` triggers the sync. This matches the `tau providers` pattern where `tau providers` lists and `tau providers add` adds.

---

## 6. Cache Layer

### 6.1 Cache file schema

```json
{
  "etag": "\"abc123\"",
  "last_modified": "Wed, 08 Jul 2026 12:00:00 GMT",
  "cached_at": "2026-07-08T12:00:00Z",
  "data": {
    "openai": {
      "gpt-5.4": {
        "context": 2000000,
        "reasoning": true,
        "max_output": 131072
      }
    }
  }
}
```

- `etag` (optional): The raw `ETag` header value from the API response, quoted as received.
- `last_modified` (optional): The raw `Last-Modified` header value.
- `cached_at` (required): ISO 8601 UTC timestamp of when the cache was written. Used in offline warning messages.
- `data` (required): The full parsed API response body — the raw `api.json` structure.

### 6.2 `_read_cache()`

```python
def _read_cache(path: Path) -> dict | None:
    """Read and validate the cache file.
    
    Returns the parsed dict on success.
    Returns None when:
      - File does not exist
      - File contains invalid JSON (deletes the corrupt file)
    
    Does NOT validate the schema beyond basic structure — 
    validation happens at point of use.
    """
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Corrupt or unreadable — delete and return None
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        typer.echo("Warning: Corrupt cache file removed.", err=True)
        return None

    if not isinstance(data, dict) or "data" not in data:
        # Schema invalid — delete and return None
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        typer.echo("Warning: Corrupt cache file removed.", err=True)
        return None

    return data
```

### 6.3 `_write_cache()`

```python
def _write_cache(path: Path, response: httpx.Response, data: dict[str, Any]) -> None:
    """Write the cache dict to disk as JSON.
    
    Creates parent directories if they don't exist.
    Extracts ETag and Last-Modified from response headers.
    """
    etag = response.headers.get("etag")
    last_modified = response.headers.get("last-modified")
    cached_at = datetime.now(timezone.utc).isoformat()

    cache_dict: dict[str, Any] = {
        "cached_at": cached_at,
        "data": data,
    }
    if etag:
        cache_dict["etag"] = etag
    if last_modified:
        cache_dict["last_modified"] = last_modified

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache_dict, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
```

### 6.4 Cache lifecycle summary

| Event | Cache action |
|-------|-------------|
| First successful API fetch | Create cache with ETag, Last-Modified, cached_at |
| 304 Not Modified | **No write** — cache unchanged, cached_at NOT updated |
| API fetch with new data | Overwrite cache (new etag, new cached_at) |
| Network error with cache | Read from cache, no write |
| Cache file corrupt | Delete, fall through to API or error |

---

## 7. Error Handling Matrix

| Failure mode | Detection | Behavior | Code path |
|---|---|---|---|
| **Network error** (timeout, DNS, refusado) | `httpx.HTTPError` exception | Cache available → `_sync_from_cache()` with reason. No cache → `SyncResult(False, source="none")` | `sync_models()` try/except |
| **HTTP non-200/304** (500, 403, etc.) | `resp.status_code` check | Cache available → `_sync_from_cache()`. No cache → `SyncResult(False, source="none")` | `sync_models()` after resp |
| **API malformed JSON** | `json.JSONDecodeError` | Cache available → `_sync_from_cache()` with `"Parse error: {exc}"`. No cache → `SyncResult(False, source="none")` | `sync_models()` try/except |
| **Cache file corrupt** | `json.JSONDecodeError` in `_read_cache` | Delete cache file, print warning to stderr, return `None` | `_read_cache()` |
| **Cache file missing, offline** | `path.exists()` is False + network error | `SyncResult(False, source="none")` with error message | `sync_models()` no-cache path |
| **API data missing `etag` header** | `response.headers.get("etag")` returns None | Proceed without ETag. Cache stored without `etag` field. Next sync does unconditional fetch. | `_write_cache()` |
| **External data missing fields** | `external.get("context")` returns None | Skip field — static value retained. Type validation rejects non-int/bool values silently. | `_merge_model_data()` |
| **Provider has no model_metadata** | `isinstance(provider, OpenAICodexProviderConfig)` | Skip `model_metadata` updates. Only update `context_windows`. | `_merge_external_data()` + `_merge_model_data()` |
| **Partial API data** (some models missing) | Model not found in `ext_provider.get(model_name)` | Skip model — static values retained. | `_merge_external_data()` loop |
| **Model not in Tau's model list but in external data** | Only iterates `provider.models` | Ignored. Never added. | Loop scope |
| **Empty response** (200 with `{}`) | `external_data` is empty dict | All providers skipped. `SyncResult(True, 0, 0)` | `_merge_external_data()` |
| **ETag not supported** (no ETag in response) | `etag` is None | Proceed without conditional headers next time. Cache still stores response for offline use. | `_write_cache()` |

---

## 8. File Changes

| File | Action | Lines changed |
|---|---|---|
| `src/tau_coding/models_sync.py` | **NEW** | ~250 lines |
| `src/tau_coding/cli.py` | **MODIFY** | ~12 lines (1 import + ~10 handler + 1 blank line after providers block) |
| `tests/test_models_sync.py` | **NEW** | ~300 lines |
| `tests/fixtures/models.dev.api.json` | **NEW** | ~100 lines (truncated snapshot with 2-3 providers) |

### `models_sync.py` internal module structure:

```
models_sync.py
├── Imports
├── Constants (URL, timeout, user-agent, cache path)
├── _PROVIDER_NAME_MAP
├── @dataclass SyncResult
├── sync_models()          # Public API
├── models_sync_command()  # CLI entry point
├── _merge_external_data() # Bulk merge
├── _merge_model_data()    # Single model merge
├── _resolve_provider_name()
├── _sync_from_cache()     # Cache fallback
├── _read_cache()          # Cache read + validation
├── _write_cache()         # Cache write
└── _default_cache_path()  # ~/.tau/models/cache.json
```

### `cli.py` changes:

```python
# Import (add after line 15):
from tau_coding.models_sync import models_sync_command

# Handler (add after the providers block, before setup):
    if prompt_option is None and command == "models":
        if len(positional_args) >= 2 and positional_args[1] == "sync":
            models_sync_command()
            raise typer.Exit()
```

---

## 9. Testing Design

### 9.1 Test file structure

**`tests/test_models_sync.py`**

```python
"""
Tests for tau models sync.

Uses a fixture file (tests/fixtures/models.dev.api.json) with a truncated
snapshot of the real models.dev API response (2-3 providers, ~5-10 models).
"""

from __future__ import annotations

import json
from pathlib import Path
from dataclasses import replace

import httpx
import pytest

from tau_coding.models_sync import (
    SyncResult,
    sync_models,
    _merge_model_data,
    _resolve_provider_name,
    _read_cache,
    _write_cache,
    _default_cache_path,
)
from tau_coding.provider_config import (
    ProviderSettings,
    OpenAICompatibleProviderConfig,
    AnthropicProviderConfig,
    OpenAICodexProviderConfig,
    ProviderModelMetadata,
    builtin_provider_configs,
)
```

### 9.2 Test cases

#### Snapshot/Integration Tests

| Test | Method | What it verifies |
|------|--------|-----------------|
| `test_sync_from_api_snapshot` | Mock `httpx.Client` to return fixture data. Call `sync_models()` with realistic `ProviderSettings`. | `context_window` updates match fixture values. `reasoning` flags updated. `max_tokens` updated. Counts correct. |
| `test_sync_304_no_changes` | Mock returns `304` response with ETag headers. Cache file has valid data. | Returns `SyncResult(True, 0, 0, "api")`. Settings unchanged. |
| `test_sync_network_error_with_cache` | Mock raises `httpx.ConnectError`. Cache file has valid data. | Returns `SyncResult(source="cache")` with merged data. |
| `test_sync_network_error_no_cache` | Mock raises `httpx.ConnectError`. No cache file. | `SyncResult(False, source="none")`. Settings unchanged. |
| `test_sync_parse_error_with_cache` | Mock returns 200 with non-JSON body. Cache exists. | Falls back to cache. `SyncResult(source="cache")`. |
| `test_sync_parse_error_no_cache` | Mock returns 200 with non-JSON body. No cache. | `SyncResult(False, source="none", error=...)`. |

#### Cache Tests

| Test | What it verifies |
|------|-----------------|
| `test_cache_write_and_read_roundtrip` | Write cache → read back → data matches. `cached_at` is valid ISO 8601. |
| `test_read_cache_missing_file` | Returns `None`. |
| `test_read_cache_corrupt_json` | Writes invalid JSON. `_read_cache()` deletes the file and returns `None`. |
| `test_read_cache_missing_data_field` | Writes valid JSON without "data" key. Returns `None`. File deleted. |
| `test_write_cache_creates_parent_dirs` | Path in non-existent directory. Creates dirs. |

#### Merge Unit Tests

| Test | What it verifies |
|------|-----------------|
| `test_merge_model_data_context_window` | External `context` overwrites `context_windows[model]`. |
| `test_merge_model_data_reasoning` | External `reasoning` overwrites `model_metadata[model].reasoning`. |
| `test_merge_model_data_max_tokens` | External `max_output` overwrites `model_metadata[model].max_tokens`. |
| `test_merge_model_data_all_fields` | All 3 fields merge in one call. |
| `test_merge_model_data_partial_fields` | Only `context` provided → only context_window updated, reasoning/max_tokens unchanged. |
| `test_merge_model_data_no_external_data` | Empty external dict → provider unchanged (same identity). |
| `test_merge_model_data_model_not_in_provider_list` | But model IS in provider.models (should be found). Test that unlisted models are never called. |
| `test_merge_model_data_codex_provider` | `OpenAICodexProviderConfig` → only `context_windows` updated, no `model_metadata` change. |
| `test_merge_model_data_creates_metadata` | Model has no existing metadata entry → new `ProviderModelMetadata` created. |
| `test_merge_model_data_type_validation` | Invalid types (string context, null reasoning, negative max_output) → silently skipped. |
| `test_merge_model_data_no_changes_identity` | Same values as existing → returns same object (identity check). |

#### Provider Name Resolution Tests

| Test | What it verifies |
|------|-----------------|
| `test_resolve_provider_name_exact_match` | `"openai"` → exact match. |
| `test_resolve_provider_name_known_mapping` | `"xai"` → found via `_PROVIDER_NAME_MAP`. |
| `test_resolve_provider_name_case_insensitive` | `"openai"` vs `"OpenAI"` → case-insensitive match. |
| `test_resolve_provider_name_no_match` | Unknown name → `None`. |
| `test_resolve_provider_name_mapping_precedence` | Exact match wins over mapping. Mapping wins over case-insensitive. |

#### CLI Command Test

| Test | What it verifies |
|------|-----------------|
| `test_models_sync_command_success` | Patch `load_provider_settings`, `sync_models`, `save_provider_settings`. Verify output and save call. |
| `test_models_sync_command_no_changes` | `providers_updated=0, models_updated=0` → no save call. |
| `test_models_sync_command_failure` | `success=False` → error to stderr, exit code 1. |

### 9.3 Fixture file

**`tests/fixtures/models.dev.api.json`**

A truncated snapshot of the real `api.json` with 2-3 providers only. Example structure:

```json
{
  "openai": {
    "gpt-5.4": {
      "context": 2000000,
      "reasoning": true,
      "max_output": 131072
    },
    "gpt-5.4-mini": {
      "context": 1000000,
      "reasoning": false,
      "max_output": 65536
    }
  },
  "anthropic": {
    "claude-sonnet-4-6": {
      "context": 200000,
      "reasoning": true,
      "max_output": 8192
    }
  },
  "x-ai": {
    "grok-4": {
      "context": 131072,
      "reasoning": true,
      "max_output": 32768
    }
  }
}
```

### 9.4 Test helpers

```python
@pytest.fixture
def sample_settings() -> ProviderSettings:
    """Return a ProviderSettings with known test providers."""
    return ProviderSettings(
        providers=(
            OpenAICompatibleProviderConfig(
                name="openai",
                models=("gpt-5.4", "gpt-5.4-mini", "gpt-5.5"),
                default_model="gpt-5.4",
                context_windows={"gpt-5.4": 128000, "gpt-5.4-mini": 64000},
                model_metadata={
                    "gpt-5.4": ProviderModelMetadata(
                        reasoning=False,
                        context_window=128000,
                        max_tokens=4096,
                    ),
                },
            ),
            AnthropicProviderConfig(
                name="anthropic",
                models=("claude-sonnet-4-6",),
                default_model="claude-sonnet-4-6",
                context_windows={"claude-sonnet-4-6": 100000},
                model_metadata={
                    "claude-sonnet-4-6": ProviderModelMetadata(
                        reasoning=False,
                        context_window=100000,
                        max_tokens=4096,
                    ),
                },
            ),
            OpenAICodexProviderConfig(
                name="openai-codex",
                models=("gpt-5.5", "gpt-5.4"),
                default_model="gpt-5.5",
                context_windows={"gpt-5.5": 128000, "gpt-5.4": 128000},
            ),
        ),
    )


@pytest.fixture
def fixture_data() -> dict:
    """Load the test fixture snapshot."""
    fixture_path = Path(__file__).parent / "fixtures" / "models.dev.api.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@pytest.fixture
def mock_http_client(fixture_data) -> httpx.Client:
    """Return an httpx.Client with a mocked transport that returns fixture data."""
    def handler(request: httpx.Request) -> httpx.Response:
        # Handle conditional request headers
        if request.headers.get("if-none-match"):
            return httpx.Response(304)
        return httpx.Response(
            200,
            headers={"etag": '"test-123"', "last-modified": "Wed, 01 Jan 2025 00:00:00 GMT"},
            json=fixture_data,
        )
    
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)
```

---

## 10. Rollout and Rollback

### Rollout

1. **Implement `models_sync.py`** as specified above
2. **Add CLI handler** in `cli.py` (~12 lines)
3. **Write tests** — snapshot test, cache tests, merge unit tests, offline tests
4. **Run existing test suite**: `uv run pytest` — verify zero regressions
5. **Manual verification**: Run `tau models sync` with network, verify output
6. **Manual verification**: Disconnect network, run `tau models sync` — verify cache fallback

### Rollback

- **Immediate**: Delete `~/.tau/models/cache.json`. Run `tau models sync` again (or don't — sync is explicit, no automatic state).
- **Full reset**: If synced data causes issues, delete `~/.tau/models/cache.json`. The static provider catalog is never modified by this feature.
- **No migration**: No data format changes, no schema migrations. The cache file is disposable.
- **Code rollback**: Revert the two-file change (`cli.py` + remove `models_sync.py`). Zero impact on any existing feature.

---

## Appendix: Key Design Rationale

### Why `sync_models()` returns `(SyncResult, ProviderSettings)` instead of mutating SyncResult

The merge produces a new immutable `ProviderSettings`. We must return it to the caller so they can decide whether to save. A frozen `SyncResult` can't carry mutable state. A tuple is the simplest Pythonic solution.

### Why identity-based change detection instead of a boolean flag

`_merge_model_data` returns the original object when no changes are needed. Callers check `merged is not current`. This is more reliable than a separate `changed` boolean because it works automatically — you can't forget to set the flag. Also, `replace()` with identical values creates a new object, so we need the explicit identity check anyway.

### Why no auto-refresh in this slice

The proposal explicitly excludes it. Auto-refresh on session start would require integration with session initialization in `session.py`, which is out of scope. Keeping sync explicit (`tau models sync`) minimizes risk and keeps the diff minimal.

### Why `OpenAICodexProviderConfig` is the only special case

It's the only `ProviderConfig` variant without a `model_metadata` field. `AnthropicProviderConfig` and `OpenAICompatibleProviderConfig` both have it. Checking `isinstance(provider, OpenAICodexProviderConfig)` is explicit and handles all current and future provider types correctly (new types without `model_metadata` would need similar treatment).
