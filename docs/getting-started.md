# Getting Started

This page explains how to install Tau, run the TUI, and work on the project.

## Requirements

Tau targets the Python version declared in `pyproject.toml` and uses `uv` for
dependency management.

## Install As a Tool

From GitHub:

```bash
uv tool install git+https://github.com/alejandro-ao/tau.git
```

From a local checkout:

```bash
uv tool install --editable .
```

Verify the installed command:

```bash
tau --version
```

## Local Development Setup

```bash
uv sync --dev --group docs
```

## Verify the CLI

```bash
uv run tau --version
```

Expected output:

```text
tau 0.1.0
```

## Configure a Provider

The default provider reads `OPENAI_API_KEY`:

```bash
export OPENAI_API_KEY="..."
```

To add an OpenAI-compatible provider:

```bash
uv run tau --provider local \
  --base-url http://localhost:11434/v1 \
  --api-key-env LOCAL_API_KEY \
  --model qwen \
  setup
```

Provider metadata is written to `~/.tau/providers.json`. API keys stay in
environment variables.

## Open the TUI

```bash
uv run tau
```

Installed as a tool:

```bash
tau
```

Tau stores indexed sessions under `~/.tau/sessions/`.

## Run One Prompt

```bash
uv run tau "explain this repository"
```

## Run tests and checks

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

## Run the documentation site locally

```bash
uv run --group docs mkdocs serve
```

Then open:

```text
http://127.0.0.1:8000
```

## Build the documentation site

```bash
uv run --group docs mkdocs build
```

The generated static website is written to `site/`.

## Deployment

Documentation is deployed to GitHub Pages from the `main` branch using the workflow in:

```text
.github/workflows/docs.yml
```

The public site is configured for:

```text
https://alejandro-ao.github.io/tau/
```
