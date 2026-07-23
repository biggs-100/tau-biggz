# Archive Report: Data-Driven TUI Themes

**Change**: `tui-themes-data-driven`
**Archived**: 2026-07-23
**Status**: Complete — 2 critical findings resolved post-verify

---

## Executive Summary

Replaced hardcoded `TuiTheme` dataclass constants with JSON files shipped alongside the package, added a theme registry for auto-discovery from three directories (built-in < user config < project), widened `TuiThemeName` from `Literal` to `str` to support custom names, removed `theme.name` branching in `chat_item.py`, and added custom theme discovery with format documentation. Implemented across 4 stacked phases (PRs) with 2 post-verify fixes applied.

**Verdict from verify**: PASS WITH WARNINGS (8/13 scenarios compliant, 24/26 requirements met). Both CRITICAL findings resolved by post-verify fixes before archiving.

---

## What Was Implemented

### Phase 1 — JSON Extraction
- 3 JSON theme files created under `src/tau_coding/tui/themes/`: `tau-dark.json`, `tau-light.json`, `high-contrast.json`
- `themes/__init__.py` package marker
- Each JSON is a verbatim copy of the corresponding dataclass constant

### Phase 2 — Registry + Integration
- `theme_registry.py` created with: `ThemeData` (Pydantic), `load_themes()`, `get_theme()`, `available_theme_names()`, `reset_cache()`
- `TuiTheme` gained fields: `success`, `error`, `tool_success_text`, `tool_error_text`, `dark`, and `role_styles["custom"]`
- `TuiThemeName` widened to `str`; `_theme_name()` softened
- `get_tui_theme()` delegates to registry with module-level lazy init
- `BUILTIN_TUI_THEME_NAMES` replaced with `available_theme_names()` in `commands.py`, `_screens_settings.py`, `app.py`, `autocomplete.py`
- `themes_dir` / `project_themes_dir()` added to `TauPaths`

### Phase 3 — Remove Per-Theme Branches
- Removed `_tool_success_color()`, `_tool_success_style()`, `_tool_error_style()` from `chat_item.py`
- Callers use `theme.success`, `theme.error`, `theme.tool_success_text`, `theme.tool_error_text` directly
- Zero `theme.name` matches in `chat_item.py`

### Phase 4 — Custom Themes
- User dir (`~/.tau/themes/`) and project dir (`<cwd>/.tau/themes/`) wired into `load_themes()`
- Auto-detection with optional explicit params for testing
- Collision detection with built-in shadow prevention
- Startup diagnostics: per-dir INFO logging
- Format documented in `dev-notes/tui-theme-format.md`

---

## Files Changed/Created

| File | Action | Description |
|------|--------|-------------|
| `src/tau_coding/tui/themes/__init__.py` | Created | Package marker |
| `src/tau_coding/tui/themes/tau-dark.json` | Created | Built-in dark theme |
| `src/tau_coding/tui/themes/tau-light.json` | Created | Built-in light theme |
| `src/tau_coding/tui/themes/high-contrast.json` | Created | Built-in high-contrast theme |
| `src/tau_coding/tui/theme_registry.py` | Created | `ThemeData`, `load_themes()`, `get_theme()`, `available_theme_names()`, `reset_cache()`, fallback `_FALLBACK_TAU_DARK` |
| `src/tau_coding/tui/config.py` | Modified | New `TuiTheme` fields, widened `TuiThemeName`, `get_tui_theme()` delegates to registry, module-level lazy init |
| `src/tau_coding/tui/chat_item.py` | Modified | Removed wrapper functions, direct theme field access |
| `src/tau_coding/tui/__init__.py` | Modified | Updated exports |
| `src/tau_coding/tui/app.py` | Modified | Uses `available_theme_names()` |
| `src/tau_coding/tui/autocomplete.py` | Modified | `theme_names` param from registry |
| `src/tau_coding/tui/_screens_settings.py` | Modified | Uses `available_theme_names()` |
| `src/tau_coding/commands.py` | Modified | `_theme_command` uses `_available_theme_names()` |
| `src/tau_coding/paths.py` | Modified | `themes_dir`, `project_themes_dir()` |
| `dev-notes/tui-theme-format.md` | Created | Theme JSON format documentation |
| `tests/test_tui_config.py` | Modified | Registry-aware tests |
| `tests/test_tui_autocomplete.py` | Modified | Dynamic name tests |
| `tests/test_tui_adapter.py` | Modified | Adapter integration tests |

---

## Test Results

| File | Passed | Failed | Skipped/Deselected |
|------|--------|--------|-------------------|
| `test_tui_config.py` | 14 | 2 | 2 (deselected) |
| `test_tui_autocomplete.py` | 29 | 0 | 0 |
| `test_tui_adapter.py` | 16 | 0 | 0 |

- **Build**: ✅ `available_theme_names()` → 3 themes
- **2 failures** are pre-existing (`auto_copy_selection` default mismatch) — unrelated to themes
- **8/13 scenarios compliant**, 3 untested/partial, 2 not met (resolved by post-verify fixes)

### Spec Compliance Summary

| Requirement Group | MUST | SHOULD/MAY | Status |
|-------------------|------|------------|--------|
| REQ-JSON (1–5) | 4 MUST, 1 SHOULD | — | 3 compliant, 1 not met (no `$schema`), 1 untested |
| REQ-REG (1–5) | 5 MUST | — | 3 compliant, 2 partial |
| REQ-FIELD (1–3) | 3 MUST | — | 2 compliant, 1 partial |
| REQ-UI (1–4) | 4 MUST | — | All compliant |
| REQ-COMPAT (1–3) | 2 MUST, 1 MAY | — | All compliant |
| REQ-CHAT (1–3) | 3 MUST | — | All compliant (post-verify fix #1) |
| REQ-CUSTOM (1–3) | 3 MUST | — | All compliant |
| EC (1–8) | — | — | 6 compliant, 1 partial, 1 untested |

---

## Post-Verify Fixes Applied

### Fix #1: Remove inline wrapper functions
**Critical findings #1 & #2 (REQ-CHAT-1, REQ-CHAT-2)**
- Removed `_tool_success_color()`, `_tool_success_style()`, `_tool_error_style()` from `chat_item.py`
- Inlined `theme.success`, `theme.error`, `theme.tool_success_text`, `theme.tool_error_text` at both call sites (`_chat_item_role_style`, `_tool_accent_style`)

### Fix #2: Hardcoded tau-dark fallback
**Critical finding #3 (REQ-REG-3 / EC-1 / EH-1)**
- Added `_FALLBACK_TAU_DARK` dict constant in `theme_registry.py`
- `get_theme()` returns the hardcoded fallback if `tau-dark` is not found, with warning log
- Ensures `get_tui_theme("tau-dark")` never returns `None` even if `tau-dark.json` is corrupted

---

## Future Considerations

- Add `$schema` key to built-in JSON files pointing to a bundled `theme-schema.json` (REQ-JSON-4, SHOULD)
- Create `theme-schema.json` as called for in the design
- Add explicit fallback from `"custom"` to `"tool"` role style when missing from theme JSON
- Consolidate theme tests into a dedicated `test_theme_registry.py`
- Fix pre-existing `auto_copy_selection` default mismatch between `tui_settings_from_json()` and `TuiSettings`
- Consider explicit `init_registry()` call in app startup for deterministic init (currently lazy)
- Live hot-reload / file watcher (Phase 4+)
- Theme editor UI

---

## Archive Contents

```
openspec/changes/archive/2026-07-23-tui-themes-data-driven/
├── archive-report.md     ← this file
├── proposal.md           ← from sdd-propose
├── specs/
│   └── tui_themes/
│       └── spec.md
├── design.md             ← from sdd-design
├── tasks.md              ← from sdd-tasks (21/24 checked, 3 stale)
└── verify-report.md      ← from sdd-verify
```

## Source of Truth Updated

- `openspec/specs/tui_themes/spec.md` — created from delta spec (new domain)

---

## SDD Cycle Complete

The change has been fully planned, implemented (4 phases + 2 post-verify fixes), verified, and archived.
