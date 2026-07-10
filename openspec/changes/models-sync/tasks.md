# Tasks: Models Sync — External Model Metadata Overlay

**Change**: `models-sync`
**Phase**: tasks
**Date**: 2026-07-08
**Artifact store**: openspec

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 460–520 |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | single-pr |
| Chain strategy | pending |

```text
Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium
```

**Line estimate breakdown**: `models_sync.py` ~250 lines, `cli.py` ~12 lines, `test_models_sync.py` ~200 lines, `fixtures/models.dev.api.json` ~50 lines.

**Risk rationale**: Isolated new file, no changes to existing core modules. The 400-line budget risk is Medium because the new file + tests total exceeds 400, but the scope is self-contained with no integration risk into existing data paths. Single PR is fine.

---

## Dependency Graph

```
Task 1 (name mapping) ──┐
                        ├──▶ Task 3 (merge logic) ──▶ Task 5 (sync_models coordinator) ──▶ Task 6 (CLI command)
Task 2 (cache I/O) ────┘                                        │
                                                                  ├──▶ Task 7 (test fixture)
                                                                  │
                                                                  └──▶ Task 8 (merge tests) ──▶ Task 9 (cache tests) ──▶ Task 10 (offline tests)
```

---

## Task 1: Provider Name Mapping

**File**: `src/tau_coding/models_sync.py` (new file, ~30 lines at the top)

**What to build**:

```
models_sync.py
├── _PROVIDER_NAME_MAP: dict[str, str]      ← TASK 1
├── _resolve_provider_name()                  ← TASK 1
```

- `_PROVIDER_NAME_MAP`: dict mapping models.dev provider IDs to Tau provider names
  - `"x-ai"` → `"xai"`
  - `"z-ai"` → `"zai"`
  - `"opencode-go"` → `"opencode-go"` (identity, acts as documentation)
- `_resolve_provider_name(tau_name: str, external_data: dict[str, Any]) -> str | None`:
  1. Exact match (`tau_name in external_data`)
  2. Reverse map lookup (iterate `_PROVIDER_NAME_MAP` to find ext_id → tau_name)
  3. Case-insensitive fallback (compare `tau_name.lower()` against all keys)
  4. Return `None` if no match

**Acceptance criteria**:
- `_resolve_provider_name("xai", {"x-ai": {...}}) → "x-ai"` (reverse mapping)
- `_resolve_provider_name("openai", {"openai": {...}}) → "openai"` (exact match)
- `_resolve_provider_name("OpenAI", {"openai": {...}}) → "openai"` (case-insensitive)
- `_resolve_provider_name("unknown-provider", {"openai": {...}}) → None`
- `_PROVIDER_NAME_MAP` is a module-level constant, not mutated

**Verification**:
```bash
# Run after implementation (tests not yet written — manual verification)
python -c "from tau_coding.models_sync import _resolve_provider_name, _PROVIDER_NAME_MAP; print('OK:', _PROVIDER_NAME_MAP); print(_resolve_provider_name('xai', {'x-ai': {}}))"
```

**Dependencies**: None (standalone utility)

---

## Task 2: Cache I/O Utilities

**File**: `src/tau_coding/models_sync.py` (append after Task 1, ~50 lines)

**What to build**:

```
models_sync.py
├── MODELS_DEV_URL, _BASE_HEADERS, _USER_AGENT   ← TASK 2 (constants)
├── _default_cache_path()                          ← TASK 2
├── _read_cache(path)                              ← TASK 2
├── _write_cache(path, response, data)            ← TASK 2
```

- `_default_cache_path() -> Path`: returns `Path.home() / ".tau" / "models" / "cache.json"`
- `_read_cache(path: Path) -> dict | None`:
  - Returns `None` if file doesn't exist
  - JSON parse → on `JSONDecodeError` or `OSError`: delete file, print warning, return `None`
  - Validate `isinstance(data, dict) and "data" in data` → if fails, delete and return `None`
  - Returns parsed dict on success
- `_write_cache(path: Path, response: httpx.Response, data: dict[str, Any]) -> None`:
  - Extract `etag` and `last_modified` from `response.headers`
  - Build cache dict: `{"cached_at": <ISO 8601 UTC>, "data": data, "etag": ..., "last_modified": ...}`
  - `mkdir(parents=True, exist_ok=True)` on parent
  - Write formatted JSON with trailing newline
- Constants: `MODELS_DEV_URL = "https://models.dev/api.json"`, `_BASE_HEADERS = {"Accept": "application/json", "User-Agent": "tau-models-sync/1.0"}`

**Acceptance criteria**:
- `_read_cache` returns `None` for non-existent path
- `_read_cache` deletes corrupt file, prints warning, returns `None`
- `_read_cache` returns valid dict for well-formed cache
- `_write_cache` creates parent directories
- `_write_cache` includes `etag` and `last_modified` only when present in response
- Cache write produces valid JSON that `_read_cache` can read back
- `_default_cache_path()` returns `~/.tau/models/cache.json`

**Verification**:
```bash
python -c "
import json, httpx
from pathlib import Path
from tau_coding.models_sync import _read_cache, _write_cache, _default_cache_path
from unittest.mock import MagicMock
resp = MagicMock(spec=httpx.Response)
resp.headers = {'etag': '\"abc\"', 'last-modified': 'Wed, 08 Jul 2026 12:00:00 GMT'}
resp.status_code = 200

p = Path('/tmp/test-tau-cache.json')
if p.exists(): p.unlink()
_write_cache(p, resp, {'openai': {'gpt-4': {'context': 100000}}})
assert p.exists(), 'cache file was not created'
d = _read_cache(p)
assert d is not None
assert d['etag'] == '\"abc\"'
assert 'cached_at' in d
p.unlink()
print('OK: cache round-trip')
"
```

**Dependencies**: None (standalone utility, but imports `httpx.Response` type)

---

## Task 3: Core Merge Logic

**File**: `src/tau_coding/models_sync.py` (append after Task 2, ~80 lines)

**What to build**:

```
models_sync.py
├── @dataclass SyncResult                      ← TASK 3
├── @dataclass ExternalModelData               ← TASK 3 (internal, optional helper)
├── _merge_model_data(provider, model_name, external, *, update_model_metadata)  ← TASK 3
├── _merge_external_data(settings, external_data)  ← TASK 3
```

- `SyncResult`:
  ```python
  @dataclass(frozen=True)
  class SyncResult:
      success: bool
      providers_updated: int
      models_updated: int
      source: Literal["api", "cache", "none"]
      error: str | None = None
  ```
- `_merge_model_data()`: Single-model merge (see design §3.3)
  - Updates `context_windows[model_name]` from external `context`
  - Updates `model_metadata[model_name]` fields (`context_window`, `reasoning`, `max_tokens`) from external `context`, `reasoning`, `max_output`
  - Type validation: `context` must be `int > 0`, `reasoning` must be `bool`, `max_output` must be `int > 0`
  - Creates new `ProviderModelMetadata` entry if one doesn't exist for this model
  - Returns same object identity (`return provider`) when no changes
  - When `update_model_metadata=False` (codex providers), only updates `context_windows`
- `_merge_external_data()`: Full settings merge (see design §3.2)
  - Iterates `settings.providers`, resolves names, merges per model
  - Returns `(SyncResult, ProviderSettings)` where the second element is the new settings (or unchanged)
  - `providers_updated` counts providers with ≥1 model changed
  - `models_updated` counts individual model merges

**Acceptance criteria**:
- `_merge_model_data` updates `context_windows` and `model_metadata` for matching models
- `_merge_model_data` returns same object when no external data matches (identity)
- `_merge_model_data` creates new `ProviderModelMetadata` entry if model exists in `provider.models` but not in `model_metadata`
- `_merge_model_data` skips `model_metadata` for `OpenAICodexProviderConfig`
- Type validation: rejects `context="not-a-number"`, `reasoning="yes"`, `max_output=-1`
- `_merge_external_data` counts correctly across multiple providers
- `_merge_external_data` returns unchanged settings when no providers match
- `SyncResult` is frozen (immutable)

**Verification**:
```bash
# Quick smoke test after implementation (not replacing full test suite)
python -c "
from tau_coding.models_sync import _merge_model_data, _merge_external_data, SyncResult
from tau_coding.provider_config import OpenAICompatibleProviderConfig, ProviderModelMetadata, ProviderSettings, replace
p = OpenAICompatibleProviderConfig(name='test', models=('m1',), context_windows={}, model_metadata={})
result = _merge_model_data(p, 'm1', {'context': 100000, 'reasoning': True, 'max_output': 8192}, update_model_metadata=True)
assert result.context_windows['m1'] == 100000
assert result.model_metadata['m1'].context_window == 100000
assert result.model_metadata['m1'].reasoning == True
assert result.model_metadata['m1'].max_tokens == 8192
print('OK: merge_model_data')
"
```

**Dependencies**: Task 1 (name mapping), Task 2 (constants)

---

## Task 4: HTTP Fetch Utilities

**File**: `src/tau_coding/models_sync.py` (append after Task 3, ~30 lines)

**What to build**:

```
models_sync.py
├── _fetch_external_data(http_client, headers) → dict    ← TASK 4
├── REQUEST_TIMEOUT = 15.0                                ← TASK 4
```

Actually, after reading the design more carefully, the fetch logic is embedded directly in `sync_models()` rather than isolated — the conditional/unconditional GET branching is too tightly coupled to the cache state. So **Task 4 is merged into Task 5**. No standalone fetch function is defined; the fetch happens inline in `sync_models()` with the conditional/unconditional branching.

**Revised**: Task 4 is absorbed into Task 5. The HTTP request logic lives in `sync_models()` directly.

**Dependencies**: N/A (merged into Task 5)

---

## Task 5: `sync_models` Coordinator

**File**: `src/tau_coding/models_sync.py` (append after Task 3, ~90 lines)

**What to build**:

```
models_sync.py
├── sync_models(settings, *, http_client, cache_path) → tuple[SyncResult, ProviderSettings]  ← TASK 5
├── _sync_from_cache(settings, cached, cache_path, *, reason) → tuple[SyncResult, ProviderSettings]  ← TASK 5
```

- `sync_models()` (see design §3.1):
  1. Resolve `cache_path` default
  2. HTTP client lifecycle: use injected one or create/close our own
  3. `_read_cache(cache_path)` — if exists:
     - Build conditional headers from `etag`/`last_modified`
     - Conditional GET → 304 = no changes, 200 = parse+merge, error = cache fallback
  4. No cache: unconditional GET → 200 = parse+merge, error = failure
  5. On parse error: try cache fallback if available, else failure
  6. On success: `_write_cache()` then `_merge_external_data()`
  7. Returns `(SyncResult, ProviderSettings)`
- `_sync_from_cache()` (see design §3.4):
  - Prints warning to stderr: `"Warning: {reason} — using cached data from {cached_at}."`
  - Calls `_merge_external_data()` with cached data
  - Returns result with `source="cache"`

**Acceptance criteria**:
- 304 response returns `(SyncResult(success=True, 0, 0, "api"), original_settings)`
- 200 response parses JSON, writes cache, merges, returns counts
- Network error with cache → returns `(SyncResult(success=True, source="cache"), merged_settings)`
- Network error without cache → returns `(SyncResult(success=False, source="none", error=...), settings)`
- Parse error with cache → cache fallback (source="cache")
- Parse error without cache → `(SyncResult(success=False, source="none"), settings)`
- HTTP client created internally when none injected, closed after use
- HTTP client NOT closed when injected (test can verify)
- 304 does NOT update cache `cached_at` (no `_write_cache` call)
- Warning goes to stderr, summary goes to stdout

**Verification** (requires mocking):
```python
# Manual smoke:
python -c "
from tau_coding.provider_config import ProviderSettings, builtin_provider_configs
from tau_coding.models_sync import sync_models
import httpx

# Injected client
with httpx.Client() as client:
    result, settings = sync_models(
        ProviderSettings(providers=builtin_provider_configs()),
        http_client=client,
        cache_path='/tmp/nonexistent-cache.json',
    )
    # Will fail if no network — expected
    print(f'source={result.source} success={result.success}')
"
```

**Dependencies**: Task 1 (name mapping), Task 2 (cache I/O), Task 3 (merge logic)

---

## Task 6: CLI Command

**File**: `src/tau_coding/cli.py` (modify, ~12 lines)

**What to build**:

1. **Add import** after line 15 (`from tau_coding.provider_add import providers_add_command`):
   ```python
   from tau_coding.models_sync import models_sync_command
   ```

2. **Add handler** in `main()` after the `providers` block (~line 276), before the `setup` block:
   ```python
   if prompt_option is None and command == "models":
       if len(positional_args) >= 2 and positional_args[1] == "sync":
           models_sync_command()
           raise typer.Exit()
   ```

And in `models_sync.py`, add `models_sync_command()` (if not already done as part of Task 5):

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
        # 304 — only "Already up to date."
        if result.source == "api" and result.providers_updated == 0 and result.models_updated == 0:
            typer.echo("Already up to date.")
            return

        # Everything else — save if changes, print summary
        if result.providers_updated > 0 or result.models_updated > 0:
            save_provider_settings(updated_settings)

        typer.echo(f"Updated {result.providers_updated} providers ({result.models_updated} models)")
        return

    # Hard failure
    error_msg = result.error or "Unknown error"
    typer.echo(f"Error: {error_msg}", err=True)
    raise typer.Exit(code=1)
```

**Acceptance criteria**:
- `tau models sync` triggers `models_sync_command()`
- `tau models` (no subcommand) falls through to TUI (no crash)
- `tau models sync` with network returns "Updated N providers (M models)" or "Already up to date."
- `tau models sync` without network+no cache prints error to stderr and exits with code 1
- `tau models sync` uses cache warning to stderr when falling back
- Follows existing `tau providers add` pattern exactly (`if len(positional_args) >= 2 and positional_args[1] == "add"` pattern)
- No changes to any other CLI behavior

**Verification**:
```bash
# Dry-run check (no network needed if no cache):
uv run python -m tau_coding.cli models sync --help  # should NOT crash (not a real subcommand)
uv run python -m tau_coding.cli models sync  # real execution
```

**Dependencies**: Task 5 (sync_models)

---

## Task 7: Test Fixture

**File**: `tests/fixtures/models.dev.api.json` (new, ~50 lines)

**What to build**:

A truncated snapshot of the real `https://models.dev/api.json` structure with:

- 2–3 providers (e.g., `openai`, `anthropic`, `x-ai`)
- 2–4 models per provider
- Include edge cases within the fixture:
  - Model with `reasoning: true`
  - Model with `reasoning: false`
  - Model with `context: <large number>`
  - Model with `max_output: <number>`
  - One model with `reasoning: null` (edge case for type validation)
  - One model missing `max_output` (partial data)
- Format: `{provider_name: {model_name: {context: int, reasoning: bool|null, max_output: int}}}`

Example structure:
```json
{
  "openai": {
    "gpt-5.4": {"context": 2000000, "reasoning": true, "max_output": 131072},
    "gpt-5.4-mini": {"context": 1000000, "reasoning": true, "max_output": 65536},
    "o4-mini": {"context": 1000000, "reasoning": true, "max_output": 65536}
  },
  "anthropic": {
    "claude-sonnet-4-6": {"context": 200000, "reasoning": null, "max_output": 8192},
    "claude-haiku-4-5": {"context": 200000, "reasoning": false, "max_output": 4096}
  },
  "x-ai": {
    "grok-4": {"context": 131072, "reasoning": false, "max_output": 4096}
  }
}
```

**Acceptance criteria**:
- Valid JSON parseable by `json.loads`
- Contains exactly the providers and models needed by snapshot tests
- Has edge cases: `null` reasoning, missing `max_output`, different provider name (`x-ai` maps to `xai` in Tau)

**Verification**:
```bash
python -c "import json; d = json.load(open('tests/fixtures/models.dev.api.json')); print(f'OK: {len(d)} providers, models: {sum(len(v) for v in d.values())}')"
```

**Dependencies**: None (can be created before or after any implementation task)

---

## Task 8: Snapshot Merge Tests

**File**: `tests/test_models_sync.py` (new file, ~80 lines for this section)

**What to build**:

```python
"""
Tests for tau models sync.

Uses fixtures from tests/fixtures/models.dev.api.json.
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
    _merge_external_data,
    _resolve_provider_name,
    _read_cache,
    _write_cache,
)
from tau_coding.provider_config import (
    ProviderSettings,
    OpenAICompatibleProviderConfig,
    AnthropicProviderConfig,
    OpenAICodexProviderConfig,
    ProviderModelMetadata,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "models.dev.api.json"


def _load_fixture() -> dict:
    """Load the truncated models.dev API snapshot."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
```

**Test cases**:

1. **`test_resolve_provider_name_exact_match`** — `_resolve_provider_name("openai", fixture)` returns `"openai"`
2. **`test_resolve_provider_name_mapped`** — `_resolve_provider_name("xai", fixture)` returns `"x-ai"`
3. **`test_resolve_provider_name_case_insensitive`** — verify case-insensitive fallback
4. **`test_resolve_provider_name_no_match`** — returns `None` for unknown provider
5. **`test_merge_model_data_updates_context_window`** — verify `context_windows` updated
6. **`test_merge_model_data_updates_model_metadata`** — verify all 3 metadata fields
7. **`test_merge_model_data_creates_new_metadata`** — model not in `model_metadata` gets created
8. **`test_merge_model_data_identity_when_no_match`** — returns same object for no-match
9. **`test_merge_model_data_codex_no_model_metadata`** — `OpenAICodexProviderConfig` updates only `context_windows`
10. **`test_merge_model_data_type_validation`** — invalid types silently skipped
11. **`test_merge_external_data_snapshot`** — feed fixture + realistic ProviderSettings, verify counts and values
12. **`test_sync_models_with_mocked_client_200`** — mock httpx to return 200 + fixture data, verify merge produces correct `context_window`, `reasoning`, `max_tokens`

**Acceptance criteria**:
- All tests pass with `uv run pytest tests/test_models_sync.py -v`
- Snapshot test produces correct merged values
- Type validation tests ensure bad external data doesn't corrupt settings
- Identity tests ensure unchanged providers are not replaced (same object)

**Verification**:
```bash
uv run pytest tests/test_models_sync.py -v
```

**Dependencies**: Task 1, Task 2, Task 3, Task 5, Task 7

---

## Task 9: Cache Tests

**File**: `tests/test_models_sync.py` (append after merge tests, ~60 lines)

**Test cases**:

1. **`test_read_cache_round_trip`**:
   - Write cache with `_write_cache`, read back with `_read_cache`
   - Verify all fields preserved (etag, last_modified, cached_at, data)

2. **`test_read_cache_missing_file`**:
   - `_read_cache(nonexistent_path) → None`

3. **`test_read_cache_corrupt_json`**:
   - Write invalid JSON to cache path
   - `_read_cache` deletes file and returns `None`

4. **`test_read_cache_invalid_schema`**:
   - Write valid JSON but missing `"data"` key
   - `_read_cache` deletes file and returns `None`

5. **`test_cache_not_written_on_304`**:
   - Mock HTTP to return 304
   - Verify `_write_cache` is NOT called
   - Verify `SyncResult(source="api", 0, 0)`

6. **`test_cache_etag_persistence`**:
   - Mock first request returns 200 with ETag `"abc123"`
   - Verify cache stores it
   - Mock second request with same ETag → 304

**Acceptance criteria**:
- All cache lifecycle tests pass
- Corrupt file deletion is verified (file no longer exists after `_read_cache`)
- 304 does not trigger cache write (can use a spy/mock on `_write_cache`)

**Verification**:
```bash
uv run pytest tests/test_models_sync.py -v -k "cache"
```

**Dependencies**: Task 2, Task 5, Task 7

---

## Task 10: Offline Fallback Tests

**File**: `tests/test_models_sync.py` (append after cache tests, ~60 lines)

**Test cases**:

1. **`test_offline_fallback_with_cache`**:
   - Write cache file with valid data
   - Mock `http_client.get` to raise `httpx.ConnectError`
   - Call `sync_models()` with cache path pointing to written cache
   - Verify result has `source="cache"` and `success=True`
   - Verify merged values correct

2. **`test_offline_fallback_no_cache`**:
   - No cache file
   - Mock `http_client.get` to raise `httpx.ConnectError`
   - Call `sync_models()`
   - Verify result has `success=False` and `source="none"`
   - Verify error message contains "Cannot reach models.dev"

3. **`test_parse_error_fallback_with_cache`**:
   - Write cache file with valid data
   - Mock HTTP response to return 200 with body `"not json"`
   - Call `sync_models()` with cache path
   - Verify result has `source="cache"` and `success=True`

4. **`test_parse_error_no_cache`**:
   - No cache file
   - Mock HTTP response to return 200 with body `"{broken"`
   - Call `sync_models()`
   - Verify result has `success=False`, `source="none"`, error mentions parsing

**Acceptance criteria**:
- Offline-with-cache tests show merges still happen from cache
- Offline-without-cache tests show clean failure (no crash, no partial merge)
- Parse error with cache falls back gracefully
- All tests pass with `uv run pytest -v -k "offline or fallback"`

**Verification**:
```bash
uv run pytest tests/test_models_sync.py -v -k "offline or fallback"
```

**Dependencies**: Task 5, Task 7, Task 2

---

## Task Execution Order

| Order | Task | Description | Est. lines |
|-------|------|-------------|-----------|
| 1 | Task 7 | Test fixture (can be done first) | 50 |
| 2 | Task 1 | Provider name mapping | 30 |
| 3 | Task 2 | Cache I/O utilities | 50 |
| 4 | Task 3 | Core merge logic + SyncResult | 80 |
| 5 | Task 5 | sync_models coordinator + _sync_from_cache | 90 |
| 6 | Task 6 | CLI command (cli.py + models_sync_command) | 12+15 |
| 7 | Task 8 | Snapshot merge tests | 80 |
| 8 | Task 9 | Cache tests | 60 |
| 9 | Task 10 | Offline fallback tests | 60 |

---

## Implementation Notes

### File structure for `models_sync.py`

```
src/tau_coding/models_sync.py
├── __future__ annotations
├── imports: json, dataclasses, datetime, pathlib, typing, httpx, typer
├── from tau_coding.provider_config import (...)
├── MODELS_DEV_URL = "https://models.dev/api.json"
├── _USER_AGENT = "tau-models-sync/1.0"
├── _BASE_HEADERS = {"Accept": "application/json", "User-Agent": _USER_AGENT}
├── REQUEST_TIMEOUT = 15.0
├── _PROVIDER_NAME_MAP: dict[str, str] = {"x-ai": "xai", "z-ai": "zai", ...}
├── @dataclass(frozen=True) class SyncResult
├── def sync_models(...) -> tuple[SyncResult, ProviderSettings]
├── def models_sync_command() -> None
├── def _merge_external_data(...) -> tuple[SyncResult, ProviderSettings]
├── def _merge_model_data(...) -> ProviderConfig
├── def _resolve_provider_name(...) -> str | None
├── def _sync_from_cache(...) -> tuple[SyncResult, ProviderSettings]
├── def _read_cache(path: Path) -> dict | None
├── def _write_cache(path: Path, response: httpx.Response, data: dict) -> None
└── def _default_cache_path() -> Path
```

### Key dependencies to import

```python
from tau_coding.provider_config import (
    OpenAICodexProviderConfig,
    ProviderConfig,
    ProviderModelMetadata,
    ProviderSettings,
    load_provider_settings,
    save_provider_settings,
)
from dataclasses import replace
```

### No changes to these files

- `src/tau_coding/provider_config.py` — NO modifications
- `src/tau_coding/catalog_loader.py` — NO modifications
- `src/tau_coding/provider_runtime.py` — NO modifications
- `src/tau_coding/session.py` — NO modifications
- `src/tau_coding/provider_catalog.py` — NO modifications

The only existing file modified is `cli.py` (~12 lines).
