# Apply Progress: Phase 3 Extension System

**Change**: phase3-extensions  
**Status**: ✅ Complete

---

## Completed Tasks

### Task 1: install/unload/reload extension mechanism

**File**: `src/tau_coding/extensions.py`

- [x] `install_extension(path: str) -> ExtensionInstance` — copies a .py file or package dir into a configured global extension directory, loads it, and returns the loaded instance. Cleans up on load failure.
- [x] `uninstall_extension(name: str) -> None` — calls `on_unload()`, removes from registry, deletes files from disk, and cleans up `sys.modules` cache.
- [x] `reload_extension(name: str) -> ExtensionInstance` — saves enabled state, unloads, clears `sys.modules` and bytecode cache (`__pycache__`), re-imports, restores enabled state.
- [x] `_clean_sys_modules(path: Path)` — static helper that removes `sys.modules` entries and clears `__pycache__` files, ensuring a clean re-import.

### Task 2: comprehensive example extension

**File**: `example_extensions/demo_ext.py` (new — 218 lines)

Features demonstrated:
- `@tool("demo_greet")` — AI tool that greets by name
- `@command("demo")` — slash command showing extension status
- `@on("session_start")` — logs session start to JSONL file in temp dir
- `@on("session_end")` — logs session end
- `@on("tool_call")` — monitors tool usage, blocks `rm -rf` in bash, increments counter
- `@ui_widget(zone="status-bar")` — live tool call counter display
- `on_load()` / `on_unload()` — lifecycle hooks for setup/teardown

### Task 3: tests for install/uninstall/reload

**File**: `tests/test_extensions.py` (appended — 5 new tests)

- [x] `test_install_extension_py_file` — install a .py file, verify loaded
- [x] `test_install_extension_package` — install a package dir, verify loaded
- [x] `test_uninstall_extension` — install then uninstall, verify removed
- [x] `test_reload_extension` — install, modify installed file, reload, verify changes
- [x] `test_install_twice_raises` — install same extension twice raises `ExtensionError`

---

## Files Changed

| File | Change |
|------|--------|
| `src/tau_coding/extensions.py` | Added `install_extension`, `uninstall_extension`, `reload_extension`, `_clean_sys_modules`. Fixed pre-existing ruff E501 issues. Added `contextlib` import. |
| `example_extensions/demo_ext.py` | **New** — comprehensive example extension |
| `tests/test_extensions.py` | Added 5 install/uninstall/reload tests |

---

## Verification Results

```text
$ uv run pytest tests/test_extensions.py tests/test_extension_ui.py -v --tb=short -q
24 passed in 0.94s

$ uv run ruff check src/tau_coding/extensions.py tests/test_extensions.py example_extensions/demo_ext.py
All checks passed!
```

---

## TDD Cycle Evidence

| Step | Action | Result |
|------|--------|--------|
| **RED** | Wrote 5 tests for install/uninstall/reload | 5 new tests failed with `AttributeError` (methods didn't exist) → then partially implemented methods failed with "No global extension directories configured" |
| **GREEN** | Updated tests to configure search paths in registry | All 17 extension tests passed |
| **REFACTOR** | Added `importlib.invalidate_caches()` and `__pycache__` cleanup to `_clean_sys_modules` for reliable reload | All 17 tests still pass |
| **FINAL** | Added demo_ext.py, ran full suite + ruff | 24 tests pass, ruff clean |

---

## Remaining Tasks

None. All tasks for Phase 3 extension system are complete.
