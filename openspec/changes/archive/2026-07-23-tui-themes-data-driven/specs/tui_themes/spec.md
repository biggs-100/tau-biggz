# Spec: Data-Driven TUI Themes — tui-theme-registry

## Overview

Replace hardcoded `TuiTheme` dataclass constants with JSON files shipped alongside the package, add a `ThemeRegistry` for auto-discovery, and remove `theme.name` branching in rendering. Four phases, additive across the cycle.

## Requirements

### 1. JSON Extraction — REQ-JSON

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-JSON-1 | 3 JSON files MUST exist under `src/tau_coding/tui/themes/`: `tau-dark.json`, `tau-light.json`, `high-contrast.json`. | MUST |
| REQ-JSON-2 | Each JSON file MUST contain ALL current `TuiTheme` fields verbatim (`screen_background` through `role_styles`). | MUST |
| REQ-JSON-3 | JSON files MUST NOT add, remove, or alter any color value vs. the dataclass constants they mirror. | MUST |
| REQ-JSON-4 | The JSON schema MUST include a `"$schema"` key pointing to a bundled JSON Schema file for validation. | SHOULD |
| REQ-JSON-5 | A `__init__.py` MUST exist in `src/tau_coding/tui/themes/` to make it an importable package. | MUST |

#### Scenario: JSON-JSON-1 — Verbatim copy
```
GIVEN the tau-dark dataclass constant in config.py
WHEN tau-dark.json is parsed
THEN every field value MUST match the dataclass field value exactly
```

#### Scenario: JSON-JSON-2 — File presence
```
GIVEN the installed package
WHEN listing src/tau_coding/tui/themes/*.json
THEN exactly 3 files must exist: tau-dark.json, tau-light.json, high-contrast.json
```

### 2. Theme Registry — REQ-REG

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-REG-1 | A `ThemeRegistry` class MUST exist with methods: `load_all()`, `get(name) -> Theme | None`, `available_names() -> list[str]`, `discover()`. | MUST |
| REQ-REG-2 | The registry MUST scan 3 directories in precedence order: built-in `< user config dir `< project dir. Later dirs override earlier ones on name collision. | MUST |
| REQ-REG-3 | Schema validation MUST run on every loaded JSON file. On parse failure, the registry MUST fall back to `tau-dark` for that name and log a warning. | MUST |
| REQ-REG-4 | The registry MUST detect name collisions across directories during `discover()`. Collisions MUST be resolved by highest-precedence directory winning. | MUST |
| REQ-REG-5 | `available_tui_theme_names()` (new single source of truth) MUST replace `BUILTIN_TUI_THEME_NAMES` in commands.py, autocomplete.py, app.py, and _screens_settings.py. | MUST |

#### Scenario: REG-1 — Built-in themes load
```
GIVEN a fresh ThemeRegistry with only built-in dir available
WHEN load_all() is called
THEN available_names() returns ["tau-dark", "tau-light", "high-contrast"]
```

#### Scenario: REG-2 — User theme overrides built-in
```
GIVEN a user theme "tau-dark" in user config dir with accent="#ff0000"
WHEN load_all() is called
THEN get("tau-dark").accent MUST be "#ff0000" (user dir wins)
```

#### Scenario: REG-3 — Invalid JSON falls back
```
GIVEN a malformed JSON file in the built-in dir for "tau-dark"
WHEN load_all() is called
THEN get("tau-dark") MUST return a valid tau-dark theme
AND a warning MUST be logged
```

#### Scenario: REG-4 — Unknown name returns None
```
GIVEN a loaded registry
WHEN get("nonexistent") is called
THEN None MUST be returned
```

### 3. New Theme Fields — REQ-FIELD

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-FIELD-1 | `TuiTheme` MUST gain fields: `success: str`, `error: str`, `tool_success_text: str`, `tool_error_text: str`, `dark: bool`. | MUST |
| REQ-FIELD-2 | `role_styles` MUST include key `"custom"` of type `TuiRoleStyle` with default fallback to `"tool"` style. | MUST |
| REQ-FIELD-3 | JSON files MUST include the new fields (Phase 1 files updated in Phase 2 before merge). | MUST |

#### Scenario: FIELD-1 — Dark detection
```
GIVEN a theme with dark=false (tau-light.json)
WHEN theme.dark is read
THEN it MUST be False for tau-light, True for tau-dark and high-contrast
```

#### Scenario: FIELD-2 — Success/error colors replace branches
```
GIVEN chat_item.py with theme.tool_success_text and theme.success
WHEN rendering a tool success indicator
THEN no if/else on theme.name is executed
```

### 4. UI Integration — REQ-UI

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-UI-1 | `commands.py` MUST use `available_tui_theme_names()` for `/theme` argument validation and help text. | MUST |
| REQ-UI-2 | `autocomplete.py` MUST source theme names from `available_tui_theme_names()` dynamically. | MUST |
| REQ-UI-3 | `_screens_settings.py` `ThemePickerScreen` MUST use `available_tui_theme_names()` for the picker list. | MUST |
| REQ-UI-4 | `app.py` theme initialization MUST use the registry to resolve the initial theme. | MUST |

#### Scenario: UI-1 — /theme autocomplete shows custom themes
```
GIVEN a user theme "my-custom" in the project themes dir
WHEN the user types "/theme my" in the command input
THEN "my-custom" MUST appear in autocomplete suggestions
```

### 5. Backward Compatibility — REQ-COMPAT

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-COMPAT-1 | The `TuiTheme` dataclass MUST remain as the runtime type. Registry returns `TuiTheme` instances, not raw dicts. | MUST |
| REQ-COMPAT-2 | `get_tui_theme()` MUST continue to accept a theme name string and return a `TuiTheme`. | MUST |
| REQ-COMPAT-3 | `BUILTIN_TUI_THEME_NAMES` MAY be deprecated but MUST remain importable until Phase 4. | MAY |

#### Scenario: COMPAT-1 — Existing importers unchanged
```
GIVEN code that imports TuiTheme and BUILTIN_TUI_THEME_NAMES
WHEN Phase 2 is deployed
THEN all existing imports MUST resolve without error
```

### 6. Phase 3 — Chat Item Cleanup — REQ-CHAT

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-CHAT-1 | `_tool_success_color()`, `_tool_success_style()`, `_tool_error_style()` MUST be removed from `chat_item.py`. | MUST |
| REQ-CHAT-2 | All callers MUST use `theme.tool_success_text`, `theme.tool_error_text`, `theme.success`, `theme.error` instead. | MUST |
| REQ-CHAT-3 | `theme.name` MUST NOT appear in any conditional branch in `chat_item.py`. | MUST |

### 7. Phase 4 — Custom Themes — REQ-CUSTOM

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-CUSTOM-1 | The registry MUST auto-discover JSON files from user config dir (`~/.config/tau/themes/` on Linux) and project dir (`<project>/.tau/themes/`). | MUST |
| REQ-CUSTOM-2 | Startup diagnostics MUST log: number of themes found per directory, any parse failures, and final resolved name list. | MUST |
| REQ-CUSTOM-3 | Custom theme format docs MUST be added under `dev-notes/`. | MUST |

### 8. Edge Cases — EC

| ID | Edge Case | Expected Behaviour |
|----|-----------|-------------------|
| EC-1 | JSON file has missing required field | Schema validation fails; fallback to tau-dark; warning logged |
| EC-2 | JSON file has extra unknown fields | Extra fields MUST be silently ignored (not rejected) |
| EC-3 | Themes directory does not exist | Registry MUST treat missing dir as empty, not error |
| EC-4 | Theme JSON is valid but name field differs from filename | The `name` field in JSON MUST be authoritative; registry uses it |
| EC-5 | The same theme name exists in all 3 directories | Project dir wins, then user dir, then built-in |
| EC-6 | `dark` field missing in a JSON file | Schema defaults MUST set `dark: true` (safe default) |
| EC-7 | `tool_success_text` is not a valid Rich color string | Fallback to `"#00ff00"`; warning logged |
| EC-8 | User/project dir has non-JSON files | Non-`.json` files MUST be silently skipped |

### 9. Error Handling — EH

| ID | Error | Behaviour |
|----|-------|-----------|
| EH-1 | JSON decode error (SyntaxError) | Fallback to tau-dark; warning logged per file |
| EH-2 | Permission denied on theme dir | Skip dir silently; warning logged |
| EH-3 | Permission denied on specific file | Skip file; warning logged; other files in dir still load |
| EH-4 | Circular reference or very deep nesting in JSON | Pydantic/JSON Schema validation depth limit; fallback to tau-dark |
| EH-5 | Schema file not found (bundled `.schema.json`) | Skip schema validation; warn; continue with json.load() only |
| EH-6 | Registry not initialized before `get()` | Must raise `RuntimeError("ThemeRegistry not initialized")` |

## Scenarios

### SCEN-1: Happy path — all phases connected
```
GIVEN Phase 1 JSON files exist and Phase 2 registry is wired
WHEN the app starts
THEN the registry loads 3 built-in themes
AND available_tui_theme_names() returns exactly 3 names
AND /theme autocomplete shows those 3 names
```

### SCEN-2: Phase 3 — no theme.name branches
```
GIVEN chat_item.py after Phase 3 changes
WHEN grepping for "theme.name" in chat_item.py
THEN no matches MUST be found
```

### SCEN-3: Phase 4 — custom theme from project dir
```
GIVEN a valid "my-dark.json" in <project>/.tau/themes/
WHEN the registry loads_all()
THEN available_names() includes "my-dark"
AND get("my-dark") returns the custom theme
```

## Out of Scope

- Live hot-reload / file watcher (Phase 4+)
- Theme editor UI
- Import/export
- Syntax theme generation
- Non-JSON serialization formats (YAML, TOML)
- Theme sharing or marketplace
