# Changelog

All notable changes to tau-biggz are documented in this file.

## [Unreleased]


## [0.1.10] — 2026-07-14
### Added
- `auto_copy_selection` activado por defecto — seleccionar texto con el mouse
  lo copia automáticamente al portapapeles.

## [0.1.9] — 2026-07-14
### Fixed
- Hardcoded `__version__` in `__init__.py` now reads from `importlib.metadata`
  so `tau --version` shows the correct installed version.

## [0.1.8] — 2026-07-14
### Added
- 241+ tests across 18 modules (1400 total, 88.5% coverage).
- `test_session_harness.py`, `test_tools_truncation.py`, `test_terminal_title.py`,
  `test_tools_bash.py`, `test_tools_events.py`, `test_tools_edit.py`,
  `test_markdown.py`, `test_session_compaction.py`, `test_app_runner.py`.
- Web search tool tests with httpx mocking.
- Subagent tool tests with mocked AgentHarness.
- OAuth login screen edge case tests (30 Textual pilot tests).

### Fixed
- Executor exceptions in `_wrap_tool_with_events` now return `AgentToolResult`
  instead of crashing (tools_events.py).
- Release workflow: switch from trusted publishing to API token authentication.
- `_codex_reasoning_effort` raises `ProviderConfigError` when no thinking modes
  are available instead of silently returning None (provider_runtime.py).
- Monkeypatch targets in test_tui_app.py after app.py → app_runner.py refactor.
- Ruff auto-fixes across 33 files (import sorting, line wrapping, blank lines).

### Changed
- Coverage threshold raised from 70% to 80%.

## 0.1.7
_Released 2026-07-09_

### Fixed
- Fix tautological package name references (tau-ai -> tau-biggz).
- Fix version string assertions in CLI tests (0.1.2 -> 0.1.7).
- Fix update check message to reference tau-biggz instead of tau-ai.
- Fix tool count assertions in session and tool tests.
- Fix release notes metadata for versions 0.1.4 through 0.1.7.

## 0.1.6
_Released 2026-07-09_

### New
- Add offline mode (--offline flag and TAU_OFFLINE env var).
- Add tool sandboxing with SandboxConfig and path validation.
- Add trust store for persistent tool approval decisions.
- Add extension UI widget registration (status-bar support).
- Add CI pipeline with matrix strategy and coverage reporting.
- Add TUI integration tests and end-to-end session tests.

### Changed
- Update CLI reference documentation.
- Update extension development docs with UI widget API.

### Fixed
- Fix UnicodeEncodeError in terminal title on Windows.
- Fix FakeSession drift in TUI test stubs.

## 0.1.5
_Released 2026-07-08_

### New
- Add package manager (tau package install/remove/list).
- Add RPC mode (tau --rpc) with JSONL protocol over stdin/stdout.
- Add formal SDK exports and developer documentation.
- Add SYSTEM.md / APPEND_SYSTEM.md support for harness system prompt.
- Add install scripts for Linux/macOS (install.sh) and Windows (install.ps1).

### Changed
- Extend harness system prompt assembly to support SYSTEM.md files.

### Fixed
- Fix __version__ sync between pyproject.toml and __init__.py.

## 0.1.4
_Released 2026-07-08_

### New
- Add OpenCode subscription provider support with Bearer authentication.
- Add models.dev metadata sync for automatic model catalog updates.
- Add automatic thinking level mapping for reasoning models.

### Changed
- Improve provider model scoping for thinking-level detection.
- Update model catalog with correct context windows for deepseek models.

### Fixed
- Fix model lookup path resolution for nested provider configs.
- Fix field nesting issues in model metadata (limit.context).
- Fix 304 merge handling during model catalog sync.
- Fix thinking level validation at startup with empty thinking_level_map.

## 0.1.3
_Released 2026-07-07_

### New
- Add a config-driven Pi API provider catalog with user overlay support.

### Changed
- Optimistically render ordinary TUI prompt submissions to reduce perceived latency.
- Improve scoped provider/model switching performance and responsiveness.
- Migrate the documentation site to Hugo.

### Fixed
- Prevent custom prompt slash commands from appearing twice in the TUI transcript.
- Persist interrupted tool repairs correctly when resuming sessions.
- Show bad --model values as clean errors instead of tracebacks.
- Fix provider/model selection and resume mismatch edge cases.
- Hide code block scrollbars while assistant messages are streaming.

## 0.1.2
_Released 2026-07-03_

### New
- Show one-time release highlights in the TUI transcript after Tau is upgraded.
- Show the active session name in the TUI header.

### Changed
- Render assistant and thinking messages without role blocks for a cleaner transcript.
- Apply role foreground colors to streaming transcript messages.
- Clarify the PyPI release process in the developer notes.

### Fixed
- Fix autocomplete suggestion window shrinking.
- Keep pre-branch context when branching with a summary.
- Keep session state on the active branch when persisting messages.

## 0.1.1
_Released 2026-06-26_

### New
- Check PyPI for Tau updates on startup.
- Route OpenAI gpt-5.5, gpt-5.4, and codex models to the /v1/responses API.
- Add the /system command for viewing the active system prompt.
- Add prompt history recall with the Up key.

### Changed
- Lower the Python requirement to 3.12.
- Render transcript messages as full-height role blocks.

### Fixed
- Restore streaming transcript scrollback.
- Fix TUI code block horizontal scrolling.
- Fix autocomplete suggestion viewport sizing.
- Disable TUI text selection while streaming.
- Guard Markdown selection until blocks are mounted.
- Validate conflicting session flags in the CLI.
- Stabilize CI checks.
