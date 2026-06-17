# Tau

Tau is a Python implementation of Pi's minimalist coding-agent harness architecture.

The project is being built in documented phases. Tau includes a `tau` console
command with a Textual TUI, print-mode prompts, durable home-directory sessions,
skills, project context discovery, and OpenAI-compatible provider configuration.

## Install

```bash
uv tool install git+https://github.com/alejandro-ao/tau.git
tau --version
```

For local development:

```bash
uv sync --dev --group docs
uv run tau --version
```

## First Run

```bash
export OPENAI_API_KEY="..."
tau
```

Run one prompt without opening the TUI:

```bash
tau "explain this repo"
```

## Development

```bash
uv sync --dev --group docs
uv run tau --version
OPENAI_API_KEY=... uv run tau "explain this repo"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy

# Documentation site
uv run --group docs mkdocs serve
```

See `docs/installation.md` and `docs/configuration.md` for provider setup,
session storage, resources, project context, and install details.
