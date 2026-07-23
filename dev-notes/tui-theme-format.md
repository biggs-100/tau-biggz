# Tau TUI Theme Format

Tau themes are JSON files. Each file defines a named theme with colors, syntax highlighting, and per-role styles.

## Discovery

Themes are loaded from three directories in order of precedence (lowest first):

| Directory | Type | Precedence |
|-----------|------|------------|
| `src/tau_coding/tui/themes/` | Built-in (shipped with Tau) | Base |
| `~/.tau/themes/` | User | Medium |
| `.tau/themes/` (project root) | Project | Highest |

Custom themes cannot shadow a built-in name — if a user or project theme
uses the same name as a built-in, it is silently skipped with a log warning.
If a custom name appears in both user and project dirs, the project definition
wins (also with a warning).

Non-existent directories are silently ignored. Invalid JSON files are skipped
with a log warning (non-fatal).

## File naming

Each theme file must have a `.json` extension. The `name` field inside the JSON
is the canonical identifier; the filename is cosmetic.  By convention, the
filename matches the `name` field: `{name}.json`.

## Schema

```json
{
  "name": "my-theme",
  "dark": true,
  "syntax_theme": "ansi_dark",
  "colors": {
    "screen_background": "#000000",
    "screen_text": "#d8dee9",
    "chrome_background": "#000000",
    "chrome_text": "#d8dee9",
    "muted_text": "#667085",
    "sidebar_background": "#000000",
    "border": "#141922",
    "transcript_background": "#000000",
    "prompt_background": "#101419",
    "prompt_text": "#e5e7eb",
    "prompt_border": "#2d3748",
    "autocomplete_background": "#000000",
    "accent": "#db945a",
    "highlight_background": "#a7f3f0",
    "highlight_text": "#061a1a",
    "markdown_heading": "#db945a",
    "markdown_table_header": "#7b7b7b",
    "markdown_table_border": "#7b7b7b",
    "markdown_inline_code": "#759e95",
    "markdown_code_block_background": "#161b21",
    "markdown_link": "#93c5fd",
    "markdown_bullet": "#db945a",
    "completion_selected": "bold #061a1a on #a7f3f0",
    "completion_selected_description": "#123333 on #a7f3f0",
    "completion_description": "#667085",
    "success": "#4ade80",
    "error": "#ff4f4f",
    "tool_success_text": "#4ade80",
    "tool_error_text": "#ff4f4f"
  },
  "roles": {
    "user": {
      "border": "#7c8ea6",
      "body": "#d8dee9 on #000000"
    },
    "assistant": {
      "border": "#6ea6a0",
      "body": "#d8dee9 on #000000"
    },
    "tool": {
      "border": "#8a7a52",
      "body": "#cbd5e1 on #000000"
    },
    "error": {
      "border": "#ff4f4f",
      "body": "#ffb4b4 on #000000"
    },
    "status": {
      "border": "#526070",
      "body": "#aab4c2 on #000000"
    },
    "thinking": {
      "border": "#4b5563",
      "body": "#9ca3af on #000000"
    },
    "skill": {
      "border": "#b48ead",
      "body": "#e5d4ef on #000000"
    },
    "custom": {
      "border": "#7c8ea6",
      "body": "#d8dee9 on #000000"
    },
    "branch_summary": {
      "border": "#c084fc",
      "body": "#e9d5ff on #000000"
    },
    "compaction_summary": {
      "border": "#c084fc",
      "body": "#e9d5ff on #000000"
    }
  }
}
```

## Top-level fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `str` | Yes | — | Theme identifier, must be unique across all loaded themes |
| `dark` | `bool` | No | `true` | Whether this is a dark theme (influences editor syntax theme fallback) |
| `syntax_theme` | `str` | No | `"ansi_dark"` | Pygments-compatible syntax highlighting theme name |
| `colors` | `object` | Yes | — | Map of UI color variable name → value (see below) |
| `roles` | `object` | Yes | — | Map of role name → `{ border, body }` style |

## Colors

Each color value is a CSS hex color (`#rrggbb`) or a Textual-style style string
(e.g. `"bold #0f172a on #dbeafe"` for the `completion_selected` key).

| Key | Purpose |
|-----|---------|
| `screen_background` | Main background |
| `screen_text` | Default text color |
| `chrome_background` | Chrome elements (header, footer, picker) background |
| `chrome_text` | Chrome text |
| `muted_text` | Secondary / de-emphasized text |
| `sidebar_background` | Session sidebar background |
| `border` | Generic border color |
| `transcript_background` | Chat transcript area background |
| `prompt_background` | Input prompt background |
| `prompt_text` | Input text color |
| `prompt_border` | Input border when focused |
| `autocomplete_background` | Completion popup background |
| `accent` | Accent color (prompt prefix, headings, etc.) |
| `highlight_background` | Selected/highlighted item background |
| `highlight_text` | Selected/highlighted item text |
| `markdown_heading` | Markdown heading color |
| `markdown_table_header` | Table header border/text |
| `markdown_table_border` | Table body border |
| `markdown_inline_code` | Inline code span color |
| `markdown_code_block_background` | Fenced code block background |
| `markdown_link` | Link text color |
| `markdown_bullet` | Bullet list marker color |
| `completion_selected` | Style for the selected completion item |
| `completion_selected_description` | Description for the selected completion |
| `completion_description` | Description for unselected completion items |
| `success` | Success indicator color |
| `error` | Error indicator color |
| `tool_success_text` | Text color for successful tool results |
| `tool_error_text` | Text color for failed tool results |

## Roles

Each role maps to a `{ border, body }` object. Both values can be a plain hex
color, a Textual inline style string (`"<foreground> on <background>"`), or
a combination.

| Role | Purpose |
|------|---------|
| `user` | User chat messages |
| `assistant` | Assistant chat messages |
| `tool` | Tool execution blocks |
| `error` | Error messages |
| `status` | Status / informational messages |
| `thinking` | Thinking-token displays |
| `skill` | Skill-invocation messages |
| `custom` | Fallback role (used when message role is unknown) |
| `branch_summary` | Session branch summary output |
| `compaction_summary` | Session compaction summary output |

## Examples

### Minimal custom theme

```json
{
  "name": "seafoam",
  "colors": {
    "screen_background": "#0d1b1e",
    "screen_text": "#d4e7e8",
    "chrome_background": "#0d1b1e",
    "chrome_text": "#d4e7e8",
    "muted_text": "#5a7d7e",
    "sidebar_background": "#0d1b1e",
    "border": "#1a2f33",
    "transcript_background": "#0d1b1e",
    "prompt_background": "#14262a",
    "prompt_text": "#e0ecec",
    "prompt_border": "#3a6b70",
    "autocomplete_background": "#0d1b1e",
    "accent": "#7fc1c5",
    "highlight_background": "#7fc1c5",
    "highlight_text": "#0d1b1e",
    "markdown_heading": "#7fc1c5",
    "markdown_table_header": "#5a7d7e",
    "markdown_table_border": "#2a4347",
    "markdown_inline_code": "#a3d4d7",
    "markdown_code_block_background": "#14262a",
    "markdown_link": "#a3d4d7",
    "markdown_bullet": "#7fc1c5",
    "completion_selected": "bold #0d1b1e on #7fc1c5",
    "completion_selected_description": "#1a2f33 on #7fc1c5",
    "completion_description": "#5a7d7e",
    "success": "#7fc1c5",
    "error": "#e06c75",
    "tool_success_text": "#7fc1c5",
    "tool_error_text": "#e06c75"
  },
  "roles": {
    "user": { "border": "#3a6b70", "body": "#d4e7e8" },
    "assistant": { "border": "#7fc1c5", "body": "#e0ecec" },
    "tool": { "border": "#8a7a52", "body": "#cbd5e1" },
    "error": { "border": "#e06c75", "body": "#f0c0c0" },
    "status": { "border": "#5a7d7e", "body": "#a0bebe" },
    "thinking": { "border": "#4b5563", "body": "#9ca3af" },
    "skill": { "border": "#b48ead", "body": "#e5d4ef" },
    "custom": { "border": "#3a6b70", "body": "#d4e7e8" },
    "branch_summary": { "border": "#c084fc", "body": "#e9d5ff" },
    "compaction_summary": { "border": "#c084fc", "body": "#e9d5ff" }
  }
}
```
