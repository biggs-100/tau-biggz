# Proposal: External Model Metadata Discovery

**Change**: `models-sync`  
**Status**: Draft  
**Author**: SDD propose phase  
**Date**: 2026-07-08

---

## 1. Business Problem

Tau's provider catalog (`src/tau_coding/data/catalog.toml`) is statically maintained. Model metadata — context windows, reasoning/thinking capabilities, max_tokens — becomes outdated between releases because updating it requires a manual process. Users get incorrect information about what their models can do:

- **Wrong context windows**: e.g., `deepseek-v4-flash` shows 164K in the static catalog but the real value is 1M.
- **Missing reasoning capability flags**: Users may not know a model supports reasoning/thinking unless the static entry was manually updated.
- **Stale model lists**: New model variants appear at providers weeks before they land in Tau's catalog.

## 2. Solution

Integrate an [open-source model registry API](https://models.dev/api.json) (maintained by anomalyco/OpenCode, 151 providers indexed) as an external data source that overlays on top of Tau's static catalog.

The merge is additive: external data fills gaps in the static catalog without replacing user or built-in entries. No core data structures change — the overlay feeds into the already-existing `ModelMetadata` fields (`context_window`, `reasoning`, `max_tokens`).

### Merge Strategy

```
Static catalog ──> ProviderConfig
                       │
External API ─────────> Overlay (3 fields only)
                       │
                       ▼
            ProviderConfig with enriched metadata
```

Only **3 fields** come from the external source:

| Field | External source field | Notes |
|-------|----------------------|-------|
| `context_window` | `context` | Integer, model's max context length in tokens |
| `reasoning` | `reasoning` | Boolean, whether model supports reasoning/thinking |
| `max_tokens` | `max_output` | Integer, model's max output tokens |

If the external source has data for a model, **it wins** over the static catalog. If the external source has no data for a model (provider not in models.dev, model not listed, or network failure), the static catalog value is retained — no data loss.

### Cache Layer

- **Location**: `~/.tau/models/cache.json`
- **Format**: JSON with the raw API response plus HTTP cache headers
- **Conditional fetch**: Uses `ETag`/`Last-Modified` from the API response. On subsequent requests, sends `If-None-Modified`; if the server responds 304, the cache is fresh.
- **No cache on first sync**: The file is created on first successful fetch.
- **Cache as fallback**: When offline or the API is unreachable, the cache file serves as the data source (still better than stale static data if cache was ever populated).

### Refresh Trigger

- **Explicit only**: `tau models sync` command triggers a refresh.
- **No auto-refresh**: No background timers, no hook into session start. Future work.

### Scope Boundary Per Provider

Only syncs metadata for models belonging to **providers that already exist in Tau's catalog**. If a provider is in models.dev but not in Tau, it is ignored. New providers must be added via `tau providers add` first.

Rationale: provider discovery is a separate concern. The external registry has 151 providers; Tau should not silently add providers the user never configured.

## 3. Target Users

All Tau users. This is infrastructure — no user-facing UI changes. The benefit is transparent: when users run `tau providers` or use a model, they get correct context windows and thinking capability flags without waiting for a Tau release.

## 4. Business Outcome

- **Correct context windows**: Users see real values, not stale release-time snapshots.
- **Accurate reasoning flags**: Models that support thinking are correctly labeled, enabling `provider_thinking_levels()` to return the right levels.
- **Real-time model additions**: When a provider adds a new model variant, `tau models sync` picks it up on next explicit sync.
- **No user workflow change**: The existing `tau providers` listing, session model selection, and thinking-level configuration all benefit automatically.

## 5. Current-State Gap

Evidence from the exploration:

| Model | Static catalog | Real (models.dev) |
|-------|---------------|-------------------|
| `deepseek-v4-flash` | 164,000 | 1,048,576 |
| `gpt-5-codex` | 400,000 | 2,000,000 |
| `o4-mini` | 200,000 | 1,000,000 |

These are not edge cases — they represent systematic staleness. The static catalog was generated at release time and only updated when someone manually edits `catalog.toml`.

## 6. Architecture

### New File

**`src/tau_coding/models_sync.py`**

Responsibilities:
- Fetch `https://models.dev/api.json` with conditional HTTP (ETag/If-None-Modified)
- Parse the response into a lookup structure: `{"provider_name": {"model_name": {"context": int, "reasoning": bool, "max_output": int}}}`
- Merge into the active provider configuration by updating `context_windows`, `model_metadata[].reasoning`, and `model_metadata[].max_tokens`
- Manage `~/.tau/models/cache.json` (read, write, ETag tracking)
- Handle all failure modes (network error, parse error, partial data)

Key function signatures:

```python
def sync_models(
    settings: ProviderSettings,
    *,
    http_client: httpx.Client | None = None,
    cache_path: Path | None = None,
) -> SyncResult:
    """Fetch models.dev API, merge metadata into provider settings, return summary."""

@dataclass
class SyncResult:
    success: bool
    providers_updated: int
    models_updated: int
    source: Literal["api", "cache", "none"]
    error: str | None = None
```

### Modified File

**`src/tau_coding/cli.py`**

Add a `tau models sync` subcommand. Following the existing pattern (see `tau providers` and `tau providers add` in the `main()` callback):

```python
if prompt_option is None and command == "models":
    if len(positional_args) >= 2 and positional_args[1] == "sync":
        models_sync_command()
        raise typer.Exit()
```

The `models_sync_command()` function lives in `models_sync.py` and:
1. Calls `load_provider_settings()` to get current provider config
2. Calls `sync_models()` with the settings
3. Prints a summary of what changed
4. Calls `save_provider_settings()` if changes were made

### Merge Point

The merge happens at the `ProviderSettings` level (in-memory). After `sync_models()` completes:

- `provider.context_windows[model_name]` ← external `context` (if available)
- `provider.model_metadata[model_name].reasoning` ← external `reasoning` (if available)
- `provider.model_metadata[model_name].max_tokens` ← external `max_output` (if available)

These are the same fields that already exist in `ModelMetadata` and `ProviderCatalogEntry` — no new data structures required.

### No Changes To

- `src/tau_coding/catalog_loader.py` — no new loading paths
- `src/tau_coding/provider_config.py` — no new config types or merge logic in existing code paths. The `_merge_model_metadata()` function (`provider_config.py` line ~894) already handles `reasoning`, `context_window`, `max_tokens` from metadata overlays — but this sync operates directly on the in-memory settings, not through the catalog merging path.
- `src/tau_coding/session.py` — session initialization reads from the already-merged `ProviderConfig`, no changes needed.

### `~/.tau/models/cache.json` Structure

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

## 7. Edge Cases

| Scenario | Behavior |
|----------|----------|
| **Offline / no network** | Use cache if available. If no cache, fall back to static catalog (no-op sync). Report "no network, using cached data" or "no network, no cache available". |
| **No cache yet, first sync** | Fetch from API, create cache file on success. If API unreachable with no cache, report error and exit cleanly (no settings changes). |
| **Provider not in models.dev** | Provider is skipped. Models for that provider keep their static catalog values. Reported in sync summary. |
| **Model in models.dev but not in Tau's catalog** | Ignored — sync only touches models already present in the provider's model list. |
| **Partial API data** (some models missing from response) | Only update models present in the API response. Missing models keep static values. |
| **API returns malformed JSON** | Fail gracefully, preserve existing cache, report error. |
| **ETag match (304 Not Modified)** | Skip processing, report "already up to date". |
| **Cache file corrupt** | Delete and re-fetch on next sync. If also offline, no-op. |
| **Concurrent sync** | Not handled (single-user CLI tool, fast operation). Last write wins. |

## 8. First-Slice Scope

| In scope | Out of scope (later) |
|----------|---------------------|
| `tau models sync` CLI command | Auto-refresh on session start |
| Fetch + ETag cache | Background sync daemon |
| Merge 3 fields: `context_window`, `reasoning`, `max_tokens` | Pricing sync (`input`/`output` cost) |
| In-memory merge at ProviderSettings level | Dynamic `thinking_levels` generation |
| ~/.tau/models/cache.json with conditional fetch | Provider discovery from models.dev |
| Graceful error fallback | UI changes (TUI or CLI table) |
| | Validation: letting users pick models not in their provider's model list |

## 9. Non-Goals (Explicit)

- **Auto-refresh**: No automatic background fetching. Only `tau models sync`.
- **Pricing sync**: Cost data (`input`/`output` tokens per dollar) is not synced. The external API has pricing, but it's excluded from this slice to keep scope tight.
- **Dynamic thinking_levels**: The existing `provider_thinking_levels()` already handles `reasoning=True` models via `thinking_level_map` or provider-level `thinking_levels`. No new thinking logic needed.
- **Provider discovery**: Adding a provider that exists in models.dev but not in Tau requires `tau providers add`. The sync command does not auto-add providers.
- **Changes to catalog_loader.py, provider_config.py core**: No changes to loading, validation, or core merge logic in those files. The sync operates at the `ProviderSettings` level.
- **Model list expansion**: The sync does not add new model names to `provider.models`. It only updates metadata for models already in the list.

## 10. Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| models.dev API goes down | Low | Cache fallback; graceful no-op with error message |
| models.dev API schema changes | Low | Parse defensively; `None` for missing fields → static fallback |
| Cache corruption | Low | Delete and re-fetch on next sync |
| Sync writes bad data to settings | Low | Only 3 fields, all optional; user runs `tau models sync` explicitly to overwrite |
| ETag not supported by origin | Low | Fall back to full fetch; cache still stores response for offline use |
| Merge conflicts with user overrides | None | User overrides live in `~/.tau/catalog.toml` and are loaded before sync. Sync operates on the in-memory settings after loading — it does not touch `catalog.toml` files. User overrides in `model_metadata` take precedence during `_merge_model_metadata()` in `provider_config.py`. |

## 11. Rollback

- **Quick rollback**: Delete `~/.tau/models/cache.json` and re-run `tau models sync` (or just don't run it). The sync is explicit — no automatic state change.
- **Full reset**: If synced data is problematic, the user can delete `~/.tau/models/cache.json`. The static catalog is never modified.
- **No migration**: No data format changes. No catalog.toml rewrites. No database migrations.

## 12. Success Criteria

1. **`tau models sync` fetches from models.dev API** and reports how many providers/models were updated.
2. **Context windows update correctly**: e.g., `deepseek-v4-flash` shows 1,048,576 after sync.
3. **Reasoning flags update correctly**: Models with `reasoning: true` in the external source are recognized by `provider_thinking_levels()`.
4. **Cache works**: Second consecutive sync with no changes returns "already up to date" (304).
5. **Offline fallback works**: Block network, run sync — uses cache and reports "cached data". Delete cache, run sync — reports error and no-ops.
6. **Existing tests pass**: `uv run pytest` with no regressions.
7. **No changes to `catalog_loader.py` or `session.py`**: Diff shows only `models_sync.py` (new) and `cli.py` (2-line addition).

## 13. Open Questions for the User

Antes de finalizar el proposal, tengo algunas preguntas para alinear mejor el alcance:

1. **Cache location**: Propongo `~/.tau/models/cache.json`. ¿Prefieren algo distinto, como `~/.tau/models/cache/api.json` para dejar espacio a futuros caches?

2. **Sync output format**: ¿El comando `tau models sync` debería emitir un resumen simple (`Updated 3 providers, 12 models`) o formato JSON (`--json` flag) para scripting?

3. **Models.dev reliability**: Si models.dev está caído en el momento del sync pero tenemos cache, ¿mostramos un warning o silenciamos? Hoy propongo warning visible.

4. **Testing strategy**: ¿Aceptan test contra un snapshot/local del api.json de models.dev para no depender de red en tests?

5. **Model list sync** (futuro): En el futuro, cuando sync también pueda agregar modelos nuevos a `provider.models`, ¿prefieren que sync sea una operación aparte (`tau models sync --include-new-models`) o que se decida por provider?
