# Proposal: Data-Driven TUI Themes

## Intent

Eliminate hardcoded `TuiTheme` dataclass constants by shipping built-in themes as JSON files, adding auto-discovery from user/project directories, and removing `theme.name` branching in rendering logic. This unblocks custom themes and aligns tau-biggz with upstream Tau's data-driven approach.

## Scope

### In Scope
- Export 3 built-in themes as JSON in `src/tau_coding/tui/themes/`
- `ThemeRegistry` — auto-discovery from 3 directories with precedence (built-in < user < project)
- New theme fields: `success`, `error`, `tool_success_text`, `tool_error_text`, `dark`, role `"custom"`
- `available_tui_theme_names()` — single source of truth replacing `BUILTIN_TUI_THEME_NAMES`
- Schema validation with fallback to tau-dark on parse failure
- Collision detection (name conflicts across directories)
- Phase 3 removes `theme.name` conditionals in `chat_item.py`

### Out of Scope
- Live hot-reload / file watcher
- Theme editor UI
- Import/export
- Syntax theme generation

## Capabilities

### New Capabilities
- `tui-theme-registry`: Theme file discovery, loading, schema validation, precedence resolution, and name-based lookup

### Modified Capabilities
None

## Approach

Four phases, each a separate PR:

1. **Phase 1 — JSON extraction** (~50 lines new). Copy 3 built-in color values verbatim into JSON files under `src/tau_coding/tui/themes/`. Add `__init__.py`. Pure additive — no code changes.
2. **Phase 2 — Theme registry** (~200 lines new, ~80 modified). Add `ThemeRegistry` and `ThemeLoader` in `src/tau_coding/tui/theme_registry.py`. Schema validation. Replace `_theme_name()`, `get_tui_theme()`, `BUILTIN_TUI_THEME_NAMES`. Add new fields. Update `commands.py`, `autocomplete.py`, `app.py`, `_screens_settings.py`, `__init__.py`.
3. **Phase 3 — Remove per-theme branches** (~30 lines modified in `chat_item.py`). Fold `_tool_success_color()`, `_tool_success_style()`, `_tool_error_style()` into theme data. No `theme.name` if/else remains.
4. **Phase 4 — Custom themes** (~40 lines new). Wire user and project theme directories. Document format in `dev-notes/`.

## Affected Areas

| Area | Impact | Description |
|------|--------|------------|
| `src/tau_coding/tui/themes/` | New | Package with 3 JSON files |
| `src/tau_coding/tui/config.py` | Modified | Replace literal checks with registry call |
| `src/tau_coding/tui/chat_item.py` | Modified | Remove `theme.name` branches |
| `src/tau_coding/tui/__init__.py` | Modified | Update exports |
| `src/tau_coding/tui/app.py` | Modified | Use `available_tui_theme_names()` |
| `src/tau_coding/tui/autocomplete.py` | Modified | Dynamic theme names |
| `src/tau_coding/tui/_screens_settings.py` | Modified | Dynamic theme names |
| `src/tau_coding/commands.py` | Modified | Use `available_tui_theme_names()` |
| `src/tau_coding/paths.py` | Modified | Add `themes_dir` property |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Color drift in JSON migration | Low | Copy verbatim, diff against dataclass values |
| Invalid custom theme crashes app | Med | Catch validation, fallback to tau-dark |
| Backward compat for `TuiTheme` importers | Med | Keep dataclass as runtime type; registry returns same shape |

## Rollback Plan

- Phase 1: delete JSON files — no code impact
- Phase 2+3: revert `config.py` and `chat_item.py` to current state; registry code removed
- Phase 4: remove `themes_dir` from `paths.py`

## Dependencies

None. JSON files ship with the package.

## Success Criteria

- [ ] All 3 built-in themes render identically before and after migration
- [ ] `/theme` autocomplete shows user/project themes from custom dirs
- [ ] Invalid custom JSON theme falls back to tau-dark without traceback
- [ ] `theme.name` no longer appears in `chat_item.py`
