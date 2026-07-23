# Design: Data-Driven TUI Themes

## Technical Approach

Replace hardcoded `TuiTheme` dataclass constants with JSON files auto-discovered from three directories (built-in < user config < project). A `ThemeRegistry` singleton provides name resolution, schema validation with fallback, and a single source of truth for `available_tui_theme_names()`. Four additive phases preserve backward compat through the cycle.

## Architecture Decisions

### Decision: Registry lifecycle

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Pure singleton | Hidden state in tests, but accessible from `commands.py` (non-tui package) | **Singleton** (module-level, initialized by app) |
| Passed through TUI | Clean DI but `_theme_command` in `tau_coding/commands.py` cannot reach it without protocol changes | N/A |

**Rationale**: `_theme_command` lives in `tau_coding/commands.py` — outside the TUI package. A singleton with lazy init avoids widening `CommandContext`. The app calls `init_registry()` at startup from `TauTuiApp.__init__` or `app_runner`. Expose via `get_registry()` and convenience function `available_tui_theme_names()`.

### Decision: Validation approach

| Option | Tradeoff | Decision |
|--------|----------|----------|
| `jsonschema` lib | Extra dep, separate schema file | — |
| **Pydantic model** | Already a dep, field-level errors, integrates with `TuiTheme` | **Pydantic** |
| Manual dict checks | Verbose, no type safety | — |

**Rationale**: `pydantic>=2.0` is already in `pyproject.toml`. A `ThemeData` pydantic model mirrors `TuiTheme` fields with defaults (`dark: bool = True`, `tool_success_text: str = "#00ff00"`, `role_styles["custom"]` fallback). Parse → validate → convert to `TuiTheme`. Keep `theme-schema.json` for external documentation only.

### Decision: JSON filename convention

| Option | Tradeoff | Decision |
|--------|----------|----------|
| `{name}.json` | Simple, but filename ≠ name field mismatch possible | **`{name}.json`** |
| `{uuid}.json` with metadata | Over-engineered | — |

**Rationale**: Filename = theme name. The `name` field in JSON is authoritative (EC-4); if absent, derive from filename stripping `.json`. Built-in files: `tau-dark.json`, `tau-light.json`, `high-contrast.json`.

### Decision: `tui.json` theme field migration

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Keep `TuiThemeName` literal | Breaks on custom theme names | — |
| **Widen to `str`** | Backward compat for existing `tui.json` values | **`TuiThemeName = str`** (deprecate literal) |

**Rationale**: Phase 2 widens `TuiThemeName` from `Literal` to `str`. The `_theme_name()` validator drops the hardcoded name check; validation happens at `get_tui_theme()` time via registry. Old `tui.json` values ("tau-dark", etc.) continue to work. `BUILTIN_TUI_THEME_NAMES` stays as a tuple of known names for backward compat.

## Data Flow

```
TauTuiApp.__init__()
  └→ init_registry(package_dir, user_dir, project_dir)
       └→ discover() → scan *.json in each dir
            └→ load_all() → parse + pydantic validate → TuiTheme[]
                 ├→ get(name) → TuiTheme | None
                 ├→ available_names() → list[str]
                 └→ fallback: tau-dark on parse failure

Consumers:
  get_tui_theme()        → wraps get_registry().get()
  available_tui_theme_names() → wraps get_registry().available_names()
  _set_tui_theme(name)   → validates via get_tui_theme(), falls back to tau-dark
  _theme_command()       → uses available_tui_theme_names()
  build_completion_state() → receives theme_names param
  ThemePickerScreen()    → uses available_tui_theme_names()
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/tau_coding/tui/themes/__init__.py` | Create | Makes `themes/` a package |
| `src/tau_coding/tui/themes/tau-dark.json` | Create | Built-in dark theme verbatim copy |
| `src/tau_coding/tui/themes/tau-light.json` | Create | Built-in light theme verbatim copy |
| `src/tau_coding/tui/themes/high-contrast.json` | Create | Built-in high-contrast verbatim copy |
| `src/tau_coding/tui/themes/theme-schema.json` | Create | Pydantic-derived schema for docs |
| `src/tau_coding/tui/theme_registry.py` | Create | `ThemeRegistry`, `ThemeData` model, `init_registry()`/`get_registry()`, `available_tui_theme_names()` |
| `src/tau_coding/tui/config.py` | Modify | Widen `TuiThemeName` to `str`; add `success`, `error`, `tool_success_text`, `tool_error_text`, `dark` fields; add `role_styles["custom"]`; update `get_tui_theme()` to use registry |
| `src/tau_coding/tui/chat_item.py` | Modify | Remove `_tool_success_color()`, `_tool_success_style()`, `_tool_error_style()`; use new theme fields |
| `src/tau_coding/tui/__init__.py` | Modify | Export `available_tui_theme_names()`, `ThemeRegistry` |
| `src/tau_coding/tui/app.py` | Modify | Call `init_registry()`; use `available_tui_theme_names()` in `_build_completion_state()` |
| `src/tau_coding/tui/app_helpers.py` | Modify | Pass `theme_names` from registry |
| `src/tau_coding/tui/_screens_settings.py` | Modify | Use `available_tui_theme_names()` in `ThemePickerScreen` |
| `src/tau_coding/commands.py` | Modify | Replace local `BUILTIN_TUI_THEME_NAMES` with `available_tui_theme_names()` |
| `src/tau_coding/tui/autocomplete.py` | Modify | Theme completions source from param (unchanged interface) |
| `src/tau_coding/paths.py` | Modify | Add `themes_dir` property and `project_themes_dir(cwd)` method |

## Interfaces / Contracts

```python
# tau_coding/tui/theme_registry.py

@dataclass(frozen=True, slots=True)
class ThemeData:
    """Pydantic-like validated theme data (BaseModel subclass)."""
    name: str
    screen_background: str
    # ... all existing fields ...
    success: str = "#9cffb1"       # NEW
    error: str = "#ff4f4f"          # NEW
    tool_success_text: str = "#00ff00"  # NEW
    tool_error_text: str = "#ff4f4f"    # NEW
    dark: bool = True               # NEW

class ThemeRegistry:
    def discover(self) -> None: ...
    def load_all(self) -> None: ...
    def get(self, name: str) -> TuiTheme | None: ...
    def available_names(self) -> list[str]: ...

def init_registry(
    builtin_dir: Path,      # src/tau_coding/tui/themes/
    user_dir: Path | None,   # ~/.config/tau/themes/
    project_dir: Path | None, # <cwd>/.tau/themes/
) -> None: ...

def get_registry() -> ThemeRegistry: ...   # raises RuntimeError if uninit
def available_tui_theme_names() -> list[str]: ...  # convenience
```

## Phase Implementation Plan

### Phase 1 — JSON Extraction
- Copy 3 built-in `TuiTheme` dataclass constants verbatim into `themes/tau-dark.json`, `themes/tau-light.json`, `themes/high-contrast.json`
- Add `themes/__init__.py`
- Add `theme-schema.json` for documentation
- Pure additive: test by parsing JSON + asserting each field matches the dataclass

### Phase 2 — Registry + Integration
- Create `theme_registry.py`: `ThemeData` pydantic model, `ThemeRegistry` class, `init_registry()`/`get_registry()` singleton
- Update `TuiTheme` dataclass: add `success`, `error`, `tool_success_text`, `tool_error_text`, `dark`, `role_styles["custom"]`
- Widen `TuiThemeName` to `str`; soften `_theme_name()` validator
- Update `get_tui_theme()` to call registry
- Wire `init_registry()` in `TauTuiApp.__init__` or app runner
- Replace `BUILTIN_TUI_THEME_NAMES` refs with `available_tui_theme_names()` in `commands.py`, `_screens_settings.py`, `app.py`
- Update JSON files to include new fields
- Add `themes_dir` and `project_themes_dir()` to `TauPaths`

### Phase 3 — Remove Per-Theme Branches
- Remove `_tool_success_color()`, `_tool_success_style()`, `_tool_error_style()` from `chat_item.py`
- Use `theme.success`, `theme.error`, `theme.tool_success_text`, `theme.tool_error_text` directly
- Verify no `theme.name` conditionals remain in `chat_item.py`

### Phase 4 — Custom Theme Discovery
- Wire user dir `~/.config/tau/themes/` and project dir `<cwd>/.tau/themes/` into `init_registry()`
- Add startup diagnostics: per-directory count, parse failures, final name list
- Document format in `dev-notes/tui-theme-format.md`

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `ThemeRegistry` load/discover/get/available | Pydantic model + fake dirs via `tmp_path` |
| Unit | Schema validation (missing fields, extra fields, bad colors, `dark` default) | `ThemeData` model validation |
| Unit | Fallback on parse failure (bad JSON, permission denied, missing file) | `tmp_path` with mock files |
| Unit | Collision resolution across 3 dirs | 3 `tmp_path` dirs, same name, verify precedence |
| Unit | `available_tui_theme_names()` integration with autocomplete | Param injection |
| Unit | `chat_item.py` post-Phase 3: all 4 tool-color fields render without name check | Grep assertion, snapshot |
| Unit | `tui.json` backward compat: old theme values still resolve | `_theme_name()` with "tau-dark" |
| Integ | Registry + `get_tui_theme()` round-trip | Load JSON dir, get theme, check fields |
| Integ | `TuiSettings.resolved_theme` with custom name | Inject registry, verify name resolves |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. Theme loading reads JSON files and validates data only.

## Migration / Rollout

- **Phase 1**: Additive — no effect on running code. Can merge anytime.
- **Phase 2**: Atomic switch. `get_tui_theme()` delegates to registry. Old code path (`_THEMES` dict) removed. `tui.json` backward compat preserved.
- **Phase 3**: Rendering-only change. Visually identical output; green diff against snapshot tests.
- **Phase 4**: Additive to Phase 2 — just wires additional dirs. User/project themes are opt-in (place a file).

## Open Questions

- [ ] Do any external consumers import `TuiThemeName` or `BUILTIN_TUI_THEME_NAMES` from the `tau_coding.tui` public API (website/docs users)?
- [ ] Should `project_themes_dir(cwd)` resolve against `.tau/themes/` or `.tau/tui/themes/`? (Following `.tau/skills/` pattern → `.tau/themes/`)
- [ ] Pydantic model name: `ThemeData`? `ThemeModel`? `ThemePayload`?
