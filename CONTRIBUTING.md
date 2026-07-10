# Contributing to tau-biggz

## Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)

### First-time setup

```bash
git clone https://github.com/biggs-100/tau-biggz.git
cd tau-biggz
uv sync --dev
```

### Running tests

```bash
# Full test suite
uv run pytest

# Specific test file
uv run pytest tests/test_agents.py -v

# With coverage
uv run pytest --cov=tau_ai --cov=tau_agent --cov=tau_coding

# TUI tests (Linux: use xvfb-run)
xvfb-run uv run pytest tests/test_tui_app.py -m tui
```

### Linting and formatting

```bash
# Lint
uv run ruff check .

# Format
uv run ruff format --check .

# Type-check
uv run mypy .
```

## Architecture

Tau preserves Pi's core separation of concerns:

```text
tau_ai      provider/model streaming layer
tau_agent   portable agent harness, loop, tools, events, sessions
tau_coding  CLI app, resources, skills, extensions, commands, TUI
```

Keep the core agent packages (`tau_ai`, `tau_agent`) independent of:
- Textual, Rich, or any rendering framework
- Session file locations
- Application-specific resource loading
- CLI behavior and provider setup UX

## Coding Guidelines

### Commits

- Use [conventional commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`
- Keep commits atomic: one coherent feature, fix, docs update, refactor, or cleanup per commit
- Never add AI attribution (no "Co-Authored-By")

### Tests

- New features require tests
- Bug fixes require a regression test
- Use `@pytest.mark.anyio` for async tests
- Use `tmp_path` fixture for file I/O tests
- Use `monkeypatch` for environment/test isolation

### Code style

- Target Python 3.12+
- Typed dataclasses or schema models for core messages, events, tools, and sessions
- Keep async boundaries explicit
- Use `uv run python` or `uv run pytest` so commands use the project environment

## Pull Request Process

1. Ensure all tests pass: `uv run pytest`
2. Ensure lint passes: `uv run ruff check .`
3. Ensure formatting passes: `uv run ruff format --check .`
4. Update CHANGELOG.md with your changes
5. Open a PR with a clear description of the change and its motivation

## Project Layout

```text
src/
  tau_ai/          # Provider/model streaming
  tau_agent/       # Portable agent harness
  tau_coding/      # CLI, TUI, resources, extensions
tests/             # Test suite
  integration/     # Integration tests (FakeProvider -> real tools)
website/           # Hugo documentation site
dev-notes/         # Build journals, ADRs, design docs
```

## Documentation

Each substantial change should leave behind notes under `dev-notes/` explaining:
- what was added
- why it exists
- how it maps to Pi's design
- how to test or use it

For user-facing changes, update the docs under `website/src/content/docs/`.
