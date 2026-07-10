# Models Sync Specification

## Purpose

Enable Tau users to refresh model metadata (context windows, reasoning capability, max output tokens) from the [models.dev API](https://models.dev/api.json) on demand, overlaying external data onto the static provider catalog without modifying built-in or user catalog entries.

## Requirements

### Requirement: CLI command `tau models sync`

The system MUST provide a `tau models sync` CLI command that fetches model metadata from the models.dev API and merges it into the active provider configuration.

#### Scenario: Happy path — first sync with network

- GIVEN the user has never run `tau models sync`
- AND the user has network access to `https://models.dev/api.json`
- WHEN the user runs `tau models sync`
- THEN the system fetches the API response
- AND the system creates `~/.tau/models/cache.json` with the raw API data and ETag
- AND the system updates `context_windows`, `model_metadata[].context_window`, `model_metadata[].reasoning`, and `model_metadata[].max_tokens` for each matching provider/model
- AND the system prints a summary: `"Updated {N} providers ({M} models)"`
- AND the system exits with code 0

#### Scenario: Subsequent sync with no changes (304)

- GIVEN `~/.tau/models/cache.json` exists with a valid ETag
- AND the API returns `304 Not Modified`
- WHEN the user runs `tau models sync`
- THEN the system prints `"Already up to date."`
- AND no settings are modified
- AND the cache file's `cached_at` timestamp is NOT updated

#### Scenario: No network, cache exists

- GIVEN the user has run `tau models sync` before and `~/.tau/models/cache.json` exists
- AND the network is unavailable
- WHEN the user runs `tau models sync`
- THEN the system prints `"Warning: No network — using cached data from {cached_at}."` to stderr
- AND the system merges metadata from the cache file into provider settings
- AND the system prints a sync summary

#### Scenario: No network, no cache

- GIVEN `~/.tau/models/cache.json` does NOT exist
- AND the network is unavailable
- WHEN the user runs `tau models sync`
- THEN the system prints `"Error: Cannot reach models.dev and no cache available. No changes made."` to stderr
- AND no provider settings are modified
- AND the system exits with code 1

#### Scenario: API returns malformed JSON

- GIVEN the network is available
- AND the API response body is not valid JSON
- WHEN the user runs `tau models sync`
- THEN the system prints `"Error: Failed to parse models.dev response: {parse error}"` to stderr
- AND if a cache exists, the system prints `"Falling back to cached data."` and uses the cache
- AND if no cache exists, the system prints `"No cache available. No changes made."` and exits with code 1

#### Scenario: Cache file is corrupt JSON

- GIVEN `~/.tau/models/cache.json` exists but contains invalid JSON
- WHEN the system attempts to read the cache
- THEN the system deletes the corrupt cache file
- AND prints `"Warning: Corrupt cache file removed."` to stderr
- AND falls through to fetch from the API if network is available
- OR falls through to `"No cache available. No changes made."` if network is also unavailable

### Requirement: HTTP fetch with conditional ETag

The system MUST fetch `https://models.dev/api.json` using `httpx` with conditional HTTP headers for cache efficiency.

#### Scenario: First fetch (no ETag)

- GIVEN the system has no cached ETag
- WHEN the HTTP GET request is made to `https://models.dev/api.json`
- THEN the request MUST include headers:
  - `Accept: application/json`
  - `User-Agent: tau-models-sync/1.0`
- AND the request MUST have a timeout of 15 seconds
- AND on a successful `200` response, the system extracts the `ETag` and `Last-Modified` response headers

#### Scenario: Conditional fetch (ETag present)

- GIVEN the system has a cached ETag `"abc123"` and `Last-Modified` value
- WHEN the HTTP GET request is made
- THEN the request MUST include headers:
  - `Accept: application/json`
  - `User-Agent: tau-models-sync/1.0`
  - `If-None-Match: "abc123"`
  - `If-Modified-Since: {last_modified_value}`
- AND on a `304` response, the system MUST NOT parse the response body and MUST report "Already up to date."

#### Scenario: Network failure (timeout, DNS, connection refused)

- GIVEN the network request fails with any `httpx` exception
- WHEN the system catches the exception
- THEN the system falls back to cache if available
- OR reports error and exits with code 1 if no cache

### Requirement: Cache file schema and lifecycle

The system MUST maintain a cache file at `~/.tau/models/cache.json` with a defined schema and lifecycle rules.

#### Scenario: Cache file JSON schema

- GIVEN the cache file exists
- THEN it MUST conform to this schema:

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

Where:
- `etag` (string, optional): The ETag from the API response, quoted as received
- `last_modified` (string, optional): The `Last-Modified` header value
- `cached_at` (string, required): ISO 8601 timestamp of when the cache was written
- `data` (object, required): The raw API response JSON structure, keyed by provider name → model name → metadata object with `context` (int), `reasoning` (bool), `max_output` (int)

#### Scenario: Cache write on successful fetch

- GIVEN the API returns `200` with valid JSON
- AND the data differs from the previous fetch (or no previous fetch)
- WHEN the system parses and merges the data
- THEN the system writes the full API response body plus `etag`, `last_modified`, and `cached_at` fields to `~/.tau/models/cache.json`
- AND the parent directory `~/.tau/models/` is created if it does not exist

#### Scenario: Cache NOT written on 304

- GIVEN the API returns `304 Not Modified`
- WHEN the system reports "Already up to date."
- THEN the cache file is NOT modified
- AND `cached_at` is NOT updated

#### Scenario: Cache read function returns None for missing or corrupt file

- GIVEN `~/.tau/models/cache.json` does not exist
- WHEN the system calls `_read_cache(path)`
- THEN it MUST return `None`
- GIVEN `~/.tau/models/cache.json` contains invalid JSON
- WHEN the system calls `_read_cache(path)`
- THEN it MUST delete the file and return `None`

### Requirement: Merge logic — 3 fields only

The sync MUST update exactly 3 fields per model: `context_window`, `reasoning`, and `max_tokens`. No other fields from the external API are merged.

#### Scenario: Merge updates context_windows dict

- GIVEN a provider has `context_windows = {"gpt-4": 128000}`
- AND the external data has `{"gpt-4": {"context": 2000000}}`
- WHEN the merge runs
- THEN `provider.context_windows["gpt-4"]` MUST become `2000000`
- AND the change is applied via `dataclasses.replace(provider, context_windows={**provider.context_windows, "gpt-4": 2000000})`

#### Scenario: Merge updates model_metadata reasoning

- GIVEN a provider has `model_metadata["gpt-4"] = ProviderModelMetadata(reasoning=False, context_window=128000, max_tokens=4096)`
- AND the external data has `{"gpt-4": {"reasoning": true, "context": 2000000, "max_output": 131072}}`
- WHEN the merge runs
- THEN the system creates a new `ProviderModelMetadata` with `reasoning=True`, `context_window=2000000`, `max_tokens=131072`
- AND applies it via `dataclasses.replace(provider, model_metadata={**provider.model_metadata, "gpt-4": updated_metadata})`

#### Scenario: External data wins over static catalog

- GIVEN the static catalog has `context_windows["gpt-4"] = 128000`
- AND the external data has `{"gpt-4": {"context": 2000000}}`
- WHEN the merge runs
- THEN the external value `2000000` MUST be used (external wins)

#### Scenario: No external data for a model — keep static value

- GIVEN the external data has no entry for model `claude-opus-5`
- WHEN the merge runs
- THEN `context_windows["claude-opus-5"]` MUST retain its original value
- AND `model_metadata["claude-opus-5"]` MUST retain its original values

#### Scenario: Provider not found in models.dev — skip

- GIVEN a provider named `my-custom-provider` exists in Tau but has no entry in the models.dev data
- WHEN the merge runs
- THEN the provider is skipped entirely
- AND its settings are not modified

#### Scenario: Model in models.dev but not in Tau's provider model list — ignore

- GIVEN the models.dev data contains a model `gpt-7-new` for provider `openai`
- AND `gpt-7-new` is NOT in the provider's `models` tuple
- WHEN the merge runs
- THEN the external data for `gpt-7-new` is ignored
- AND no new entry is added to `context_windows` or `model_metadata`

#### Scenario: Provider name mapping — case-insensitive fallback

- GIVEN a Tau provider has `name="openai"`
- AND the models.dev data has a key `"OpenAI"` (different case)
- WHEN the merge runs
- THEN the system MUST try an exact match first
- AND if no exact match, fall back to a case-insensitive lookup
- AND if found, use the case-insensitive match for merging

#### Scenario: Merge on OpenAICodexProviderConfig (no model_metadata)

- GIVEN a provider is of type `OpenAICodexProviderConfig` which has `context_windows` but no `model_metadata` field
- WHEN the merge runs
- THEN the system MUST update `context_windows` only
- AND skip `model_metadata` updates for that provider type
- AND continue to other providers normally

#### Scenario: Partial external data — missing fields use static values

- GIVEN the external data for a model has `{"context": 2000000}` but no `reasoning` or `max_output`
- WHEN the merge runs
- THEN `context_window` is updated to `2000000`
- AND `reasoning` retains its static catalog value
- AND `max_tokens` retains its static catalog value

### Requirement: Sync summary output

The system MUST print a text summary of the sync operation to stdout on success.

#### Scenario: Summary after successful sync

- GIVEN the sync updated 3 providers and 12 models
- WHEN the merge completes
- THEN stdout MUST contain: `"Updated 3 providers (12 models)"`

#### Scenario: Summary with no changes

- GIVEN the sync found no providers or models to update (all external data matches current values)
- WHEN the merge completes
- THEN stdout MUST contain: `"Updated 0 providers (0 models)"`

### Requirement: Key function signatures

The system MUST expose the following functions with specified signatures:

```
@dataclass(frozen=True)
class SyncResult:
    success: bool
    providers_updated: int
    models_updated: int
    source: Literal["api", "cache", "none"]
    error: str | None = None


def sync_models(
    settings: ProviderSettings,
    *,
    http_client: httpx.Client | None = None,
    cache_path: Path | None = None,
) -> SyncResult:
    """Fetch models.dev API, merge metadata into provider settings, return summary."""


def models_sync_command() -> None:
    """CLI entry point: load settings, sync, print summary, save if changed."""


def _merge_model_data(
    provider: ProviderConfig,
    model_name: str,
    external_data: dict[str, Any],
) -> ProviderConfig:
    """Return a new provider config with merged external data for one model."""


def _read_cache(path: Path) -> dict | None:
    """Read and validate the cache file. Return parsed dict or None."""


def _write_cache(path: Path, data: dict) -> None:
    """Write cache dict to disk as JSON, creating parent dirs."""
```

### Requirement: `models_sync_command` implementation

The `models_sync_command()` function MUST follow this sequence:

1. Load current settings via `load_provider_settings()`
2. Call `sync_models(settings, cache_path=Path("~/.tau/models/cache.json").expanduser())`
3. On `SyncResult(success=True, providers_updated=N, models_updated=M)`:
   - If `N > 0`: call `save_provider_settings(settings)` with the updated settings
   - Print `"Updated {N} providers ({M} models)"` to stdout
4. On `SyncResult(success=False, source="none")`: print error message to stderr, exit code 1
5. On `SyncResult(success=False, source="cache")`: print warning to stderr, print sync summary (zero counts), exit code 0 (cache read worked but was empty of matches)

#### Scenario: Load-sync-save flow

- GIVEN `load_provider_settings()` returns `ProviderSettings` with 3 providers
- AND `sync_models` returns `SyncResult(success=True, providers_updated=2, models_updated=8)`
- WHEN `models_sync_command()` runs
- THEN `save_provider_settings()` is called with the updated settings
- AND stdout contains `"Updated 2 providers (8 models)"`

#### Scenario: Sync changes nothing — no save

- GIVEN `sync_models` returns `SyncResult(success=True, providers_updated=0, models_updated=0)`
- WHEN `models_sync_command()` runs
- THEN `save_provider_settings()` is NOT called
- AND stdout contains `"Updated 0 providers (0 models)"`

### Requirement: CLI integration in `cli.py`

The system MUST add a `models` subcommand handler in `cli.py` following the existing `tau providers` pattern.

#### Scenario: `tau models sync` triggers the command

- GIVEN the user runs `tau models sync`
- WHEN the CLI parses `positional_args = ["models", "sync"]`
- THEN `command == "models"` AND `positional_args[1] == "sync"`
- AND the handler calls `models_sync_command()`
- AND raises `typer.Exit()` to stop further processing

#### Scenario: `tau models` without subcommand is ignored (falls through to TUI)

- GIVEN the user runs `tau models` with no subcommand
- WHEN the CLI parses `positional_args = ["models"]`
- THEN `command == "models"` AND `len(positional_args) == 1`
- AND no `models` handler runs (the input is treated as a prompt and opens the TUI)

### Requirement: Error handling matrix

The system MUST handle all failure modes as specified:

| Failure mode | Behavior |
|---|---|
| **Network error** (timeout, DNS, connection refused) | Use cache if available. If no cache, exit code 1 with error message to stderr. |
| **HTTP non-200/304 status** | Treat as error. Use cache if available, else exit code 1. |
| **API returns malformed JSON** | Use cache if available, else exit code 1. Error message to stderr. |
| **Cache file corrupt** | Delete cache file. If API available, re-fetch. If also offline, exit code 1. |
| **Cache file missing on network failure** | Exit code 1. Error message: "Cannot reach models.dev and no cache available." |
| **API data missing expected fields** | Skip missing fields silently. Only merge fields that are present and valid. |
| **Provider type has no model_metadata** (OpenAICodexProviderConfig) | Update context_windows only; skip model_metadata updates for that provider. |
| **ETag not supported by origin** (no ETag in response) | Proceed without conditional headers next time. Cache still stores response body. |

### Requirement: Testing plan

The test suite MUST cover the merge logic, cache lifecycle, offline behavior, and HTTP edge cases.

#### Scenario: Snapshot test — merge produces correct context_window and reasoning

- GIVEN a fixture file `tests/fixtures/models.dev.api.json` containing a truncated snapshot of the real API response
- AND a `ProviderSettings` with known provider configs
- WHEN `sync_models()` is called with a mocked HTTP client that returns the fixture data
- THEN the resulting settings MUST have correct `context_window` values for each model in the snapshot
- AND correct `reasoning` flags

#### Scenario: Cache read/write round-trip

- GIVEN a temporary path
- WHEN `_write_cache(path, data)` writes a valid cache dict
- AND `_read_cache(path)` reads it back
- THEN the returned dict MUST match the original data

#### Scenario: ETag conditional fetch

- GIVEN a cache file with an ETag
- WHEN the mocked HTTP client returns `304`
- THEN `sync_models()` MUST return `SyncResult(providers_updated=0, models_updated=0, source="api")`

#### Scenario: Offline fallback with cache

- GIVEN a cache file with valid data
- AND the mocked HTTP client raises a network exception
- WHEN `sync_models()` is called
- THEN it MUST return `SyncResult(source="cache")` with the merged results from cached data

#### Scenario: Offline fallback without cache

- GIVEN no cache file exists
- AND the mocked HTTP client raises a network exception
- WHEN `sync_models()` is called
- THEN it MUST return `SyncResult(success=False, source="none", error=...)`

#### Scenario: Unit test for `_merge_model_data` with various scenarios

- GIVEN a provider with existing `context_windows` and `model_metadata`
- WHEN `_merge_model_data(provider, "model-x", {"context": 100000, "reasoning": True, "max_output": 8192})` is called
- THEN the returned provider MUST have `context_windows["model-x"] == 100000`
- AND `model_metadata["model-x"].context_window == 100000`
- AND `model_metadata["model-x"].reasoning == True`
- AND `model_metadata["model-x"].max_tokens == 8192`

#### Scenario: Unit test — model not in provider's model list

- GIVEN a provider with `models = ("model-a", "model-b")`
- WHEN `_merge_model_data` is called for `"model-c"`
- THEN the returned provider MUST be unchanged (same object identity via `is`)

### Requirement: No changes to existing modules

The system MUST NOT modify `catalog_loader.py`, `provider_config.py` (except the three merged fields via `dataclasses.replace` at the ProviderSettings level but not the core merge logic in `_merge_provider_model_metadata`), `session.py`, or `provider_catalog.py`.

#### Scenario: Diff shows only new files and minimal CLI change

- GIVEN the implementation is complete
- WHEN checking `git diff --stat`
- THEN the diff MUST include only:
  - `src/tau_coding/models_sync.py` (new file)
  - `src/tau_coding/cli.py` (~10 lines added for models subcommand)
  - `tests/test_models_sync.py` (new file)
  - `tests/fixtures/models.dev.api.json` (new file, snapshot)

### Files

| File | Action |
|---|---|
| `src/tau_coding/models_sync.py` | NEW — all sync logic |
| `src/tau_coding/cli.py` | MODIFY — add `tau models sync` handler |
| `tests/test_models_sync.py` | NEW — tests for sync, cache, merge, offline |
| `tests/fixtures/models.dev.api.json` | NEW — truncated API snapshot for tests |
