# Tasks: Data-Driven TUI Themes

## Review Workload Forecast

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

Estimated changed lines: 450–550 across 4 PRs. Tests add ~120 lines beyond production code.

### Suggested Work Units

| Unit | PR | Focused test | Rollback boundary |
|------|----|-------------|-------------------|
| JSON extraction | PR 1 | `pytest tests/ -x -k json_verbatim` | Delete `themes/` dir |
| Registry + integration | PR 2 | `pytest tests/test_theme_registry.py -x` | Revert `theme_registry.py`, `config.py`, `paths.py`, app wiring |
| Chat branch removal | PR 3 | `pytest tests/ -x -k chat_item` | Revert `chat_item.py` |
| Custom dirs + docs | PR 4 | `pytest tests/ -x -k custom` | Revert `paths.py`, `dev-notes/` |

## Phase 1 — JSON Extraction

- [x] 1.1 Create `src/tau_coding/tui/themes/__init__.py` — empty package marker
- [x] 1.2 Create `themes/tau-dark.json` — verbatim `TAU_DARK_THEME` fields
- [x] 1.3 Create `themes/tau-light.json` — verbatim `TAU_LIGHT_THEME` fields
- [x] 1.4 Create `themes/high-contrast.json` — verbatim `HIGH_CONTRAST_THEME` fields
- [ ] 1.5 Test: parse each JSON, assert every field matches its dataclass constant

## Phase 2 — Registry + Integration

- [x] 2.1 Add to `TuiTheme` in `config.py`: `success`, `error`, `tool_success_text`, `tool_error_text`, `dark` fields + `role_styles["custom"]`
- [x] 2.2 Set new field defaults on `TAU_DARK_THEME`, `TAU_LIGHT_THEME`, `HIGH_CONTRAST_THEME`
- [x] 2.3 Widen `TuiThemeName` to `str`; soften `_theme_name()` to accept any str
- [x] 2.4 Create `theme_registry.py`: `ThemeData` (Pydantic), module-level singleton, `load_themes()`, `get_theme()`, `available_theme_names()`, `reset_cache()`
- [x] 2.5 Update `get_tui_theme()` to delegate to registry
- [x] 2.6 Wire registry in config.py via module-level lazy loading (no explicit init needed)
- [x] 2.7 Update JSON files to include new fields (done in Phase 1 — already have success, error, tool_success_text, tool_error_text, dark, custom role)
- [x] 2.8 Replace `BUILTIN_TUI_THEME_NAMES` with `available_theme_names()` in `commands.py`, `_screens_settings.py`, `app.py`
- [x] 2.9 Update `_open_theme_picker()` — `TuiThemeName` → `str`
- [x] 2.10 Add `themes_dir`/`project_themes_dir()` to `TauPaths` in `paths.py`
- [x] 2.11 Update `__init__.py` exports
- [ ] 2.12 Tests: registry load/discover via `tmp_path`, validation fallback, collision precedence, fallback on bad JSON

## Phase 3 — Remove Per-Theme Branches

- [ ] 3.1 Remove `_tool_success_color()`, `_tool_success_style()`, `_tool_error_style()` from `chat_item.py`
- [ ] 3.2 Use `theme.success/error/tool_success_text/tool_error_text` directly in `_chat_item_role_style()` and `_tool_accent_style()`
- [ ] 3.3 Test: grep `chat_item.py` for `theme.name` — zero matches; render tool-result with all 3 themes

## Phase 4 — Custom Themes

- [x] 4.1 Wire user dir (`~/.tau/themes/`) and project dir (`<cwd>/.tau/themes/`) into `load_themes()` with auto-detection and optional explicit params for testing
- [x] 4.2 Add startup diagnostics: per-dir INFO logging for each scanned directory, skipped invalid files, skipped built-in shadow, and total theme count
- [x] 4.3 Document theme format in `dev-notes/tui-theme-format.md`
- [x] 4.4 Tests: custom theme appears, built-in cannot be shadowed, project overrides user, missing dir is silent, unknown name returns None
