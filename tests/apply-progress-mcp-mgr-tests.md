# sdd-apply Progress: MCP Manager Tests

## Module 1: `tests/test_rpc.py`

**New tests added:**
- `TestReadStdin` (4 tests): `_read_stdin()` async stdin reader
  - `test_reads_json_lines` — parses JSON lines from pre-fed StreamReader
  - `test_skips_empty_lines` — skips blank lines without yielding commands
  - `test_handles_invalid_json_and_continues` — error response + continues
  - `test_connection_error_stops` — stops iteration on pipe closed
- `TestRunPrompt` (2 tests): `_run_prompt()` event streaming helper
  - `test_streams_events_to_json` — streams model events as JSON lines
  - `test_error_during_prompt` — errors caught and written as error events
- `TestRunRpcMode` (9 tests): `run_rpc_mode()` async main loop
  - `test_ready_event_at_start` — sends 'ready' event before commands
  - `test_unknown_command` — unknown command type gets error response
  - `test_cancel_without_active_task` — cancel succeeds without active task
  - `test_get_state_without_session` — get_state errors when no session
  - `test_prompt_creates_session_and_streams` — prompt creates session + streams
  - `test_prompt_empty_message_error` — empty message prompt returns error
  - `test_get_state_with_session` — get_state returns session info
  - `test_set_model_creates_session` — set_model creates session
  - `test_set_model_on_existing_session` — set_model updates existing session
  - `test_multiple_commands_in_sequence` — processes multiple commands

**Coverage:** 86% (target 60% ✓)

## Module 2: `tests/test_package_manager.py`

**New tests added:**
- `TestInstallGit` (6 tests): `_install_git()` git clone via subprocess
  - `test_successful_clone` — verifies correct command args
  - `test_clone_failure` — failed clone returns error + cleanup
  - `test_git_not_found` — FileNotFoundError handled
  - `test_clone_timeout` — TimeoutExpired handled
  - `test_already_exists` — skip clone when dest exists
  - `test_clone_failure_cleanup` — partial dir cleanup on failure
- `TestInstallLocal` (5 tests): `_install_local()` directory copy
  - `test_copy_directory` — copies with subdirs and files
  - `test_source_not_exists` — error on missing source
  - `test_source_is_file_not_dir` — error on file source
  - `test_already_exists` — error on existing dest
  - `test_copy_error_cleanup` — cleans up on copy failure
- `TestSymlinkResources` (4 tests): `_symlink_resources()` linking
  - `test_dry_run_returns_linked_paths` — returns linked resources
  - `test_dry_run_skips_existing` — marks existing as skipped
  - `test_dry_run_skips_hidden` — skips . and _ prefixed files
  - `test_empty_package_no_resources` — empty package returns empty
- `TestInstallPackageFull` (4 tests): `install_package()` full flow
  - `test_install_git_source` — git source with mocked clone
  - `test_install_local_source` — local source install
  - `test_install_local_source_not_found` — missing source error
  - `test_install_local_duplicate_name` — duplicate name error

**Coverage:** 87% (target 75% ✓)

## Module 3: `tests/test_mcp_manager.py`

**New tests added:**
- `TestMcpSearch` additions (2 tests): `mcp_search()` npm registry
  - `test_search_successful` — successful HTTP returns parsed results
  - `test_search_empty_response` — empty response returns empty list
- `TestMcpInstall` (3 tests): `mcp_install()` add server to config
  - `test_install_new` — creates config entry
  - `test_install_duplicate` — duplicate returns error
  - `test_install_simple_name` — install without npm scope
- `TestMcpRemove` (3 tests): `mcp_remove()` remove server
  - `test_remove_existing` — removes from config
  - `test_remove_nonexistent` — not-found message
  - `test_remove_last` — removes last server

**Coverage:** 94% (target 75% ✓)

## Infrastructure changes
- Added `pytest-anyio` to dev dependencies
- Created `tests/conftest.py` with anyio marker registration

## Verification
- `uv run pytest tests/test_rpc.py tests/test_package_manager.py tests/test_mcp_manager.py --tb=short -q` → 106 passed
- `uv run ruff check tests/test_rpc.py tests/test_package_manager.py tests/test_mcp_manager.py` → All checks passed
