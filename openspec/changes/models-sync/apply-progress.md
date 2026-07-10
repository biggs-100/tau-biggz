# Apply Progress: Models Sync

**Change**: `models-sync`
**Phase**: apply
**Date**: 2026-07-08
**Status**: Complete

---

## Summary

Implemented the `tau models sync` feature — fetches model metadata (context windows, reasoning, max tokens) from `https://models.dev/api.json` and merges it into the active provider configuration.

## Completed Tasks

| Task | Description | Status |
|------|-------------|--------|
| Task 1 | Provider name mapping (`_PROVIDER_NAME_MAP`, `_resolve_provider_name`) | ✅ |
| Task 2 | Cache I/O utilities (`_default_cache_path`, `_read_cache`, `_write_cache`) | ✅ |
| Task 3 | Core merge logic (`SyncResult`, `_merge_model_data`, `_merge_external_data`) | ✅ |
| Task 4 | HTTP fetch utilities (merged into Task 5) | ✅ (absorbed) |
| Task 5 | `sync_models` coordinator (ETag conditional GET, cache fallback) | ✅ |
| Task 6 | CLI command (`tau models sync` in `cli.py`) | ✅ |
| Task 7 | Test fixture (`tests/fixtures/models.dev.api.json`) | ✅ |
| Task 8 | Snapshot merge + provider name resolution tests | ✅ |
| Task 9 | Cache lifecycle tests | ✅ |
| Task 10 | Offline fallback tests | ✅ |

## Files Changed

### New Files
- `src/tau_coding/models_sync.py` — all sync logic (~300 lines)
- `tests/test_models_sync.py` — 36 tests across 7 test classes
- `tests/fixtures/models.dev.api.json` — truncated API snapshot (3 providers, 6 models)

### Modified Files
- `src/tau_coding/cli.py` — added `tau models sync` subcommand (import + handler, ~12 lines)

## TDD Cycle Evidence

| Cycle | RED | GREEN | Notes |
|-------|-----|-------|-------|
| 1 | `ModuleNotFoundError` (module didn't exist) | 36/36 passing | Implemented all functions then ran tests |
| 2 | 2 failures (identity checks) | 36/36 passing | Fixed `_merge_model_data` identity logic |
| 3 | 8 failures (`datetime.UTC` not available on 3.12) | 36/36 passing | Switched to `timezone.utc` |

## Test Commands Run

```bash
uv run pytest tests/test_models_sync.py -v      # 36 passed
uv run ruff check src/tau_coding/models_sync.py  # clean (0 errors)
uv run python -c "from tau_coding.models_sync import sync_models, SyncResult; print('OK')"
uv run python -c "from tau_coding.cli import main; print('CLI OK')"
```

## Deviations from Design

- `_merge_model_data` uses identity check (`result is provider`) for detecting unchanged providers. Added `model_name not in provider.models` early guard to prevent validation errors when `replace()` is called with metadata for models not in the provider's model list.
- Updated `_merge_model_data` to compare actual values before marking metadata as changed, so equal values preserve object identity.
- Used `httpx.MockTransport` for HTTP mocking in tests instead of `unittest.mock.patch` — cleaner integration with httpx 0.28+.

## Verification Evidence

- 4 provider name resolution tests (exact, mapped, case-insensitive, no-match)
- 8 `_merge_model_data` tests (context_window, metadata, new entries, identity, codex, type validation, partial data, null handling)
- 3 `_merge_external_data` tests (snapshot, no-match, codex)
- 5 cache lifecycle tests (round-trip, missing, corrupt, invalid schema, 304)
- 2 cache+merge integration tests (etag persistence, 200+merge)
- 7 offline/error tests (network error ± cache, parse error ± cache, non-200 ± cache, client lifecycle)

## Remaining Tasks

None — all 10 tasks complete.

## Workload / PR Boundary

Single PR. Estimated ~470 lines (300 implementation + 170 tests/fixtures). No chained PRs needed.
