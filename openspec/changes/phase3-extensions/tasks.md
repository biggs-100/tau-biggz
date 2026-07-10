# Tasks: Phase 3 Extension System

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~250 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | single-pr |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

---

## Task 1 — Install/unload/reload extension mechanism

**File**: `src/tau_coding/extensions.py`

- [x] `install_extension(path: str) -> ExtensionInstance` — copies .py/package to global dir, loads it
- [x] `uninstall_extension(name: str) -> None` — removes extension, deletes files, cleans sys.modules
- [x] `reload_extension(name: str) -> ExtensionInstance` — hot-reload with enabled-state preservation

---

## Task 2 — Comprehensive example extension

**File**: `example_extensions/demo_ext.py` (new)

- [x] `@tool("demo_greet")` — greeting tool
- [x] `@command("demo")` — status command
- [x] `@on("session_start")` / `@on("session_end")` — session logging
- [x] `@on("tool_call")` — tool monitoring with rm -rf blocking
- [x] `@ui_widget(zone="status-bar")` — tool call counter
- [x] `on_load()` / `on_unload()` — lifecycle hooks

---

## Task 3 — Add tests for install/uninstall/reload

**File**: `tests/test_extensions.py`

- [x] `test_install_extension_py_file`
- [x] `test_install_extension_package`
- [x] `test_uninstall_extension`
- [x] `test_reload_extension`
- [x] `test_install_twice_raises`

---

## Task 4 — Verification

- [x] `pytest tests/test_extensions.py tests/test_extension_ui.py` — **24 passed**
- [x] `ruff check src/tau_coding/extensions.py tests/test_extensions.py example_extensions/demo_ext.py` — **All checks passed**
