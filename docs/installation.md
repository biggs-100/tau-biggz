# Installation

Tau is packaged as a Python console application named `tau`.

## Install With uv

From a checked-out copy of the repository:

```bash
uv tool install --editable .
```

From GitHub:

```bash
uv tool install git+https://github.com/alejandro-ao/tau.git
```

Verify the installed command:

```bash
tau --version
```

## Install With pipx

```bash
pipx install git+https://github.com/alejandro-ao/tau.git
```

## First Run

Tau starts the interactive Textual TUI when no prompt is provided:

```bash
tau
```

For a one-shot print-mode prompt:

```bash
tau "explain this repository"
```

Tau needs an OpenAI-compatible provider. The default provider reads:

```bash
export OPENAI_API_KEY="..."
```

Optionally configure a custom provider:

```bash
tau --provider local \
  --base-url http://localhost:11434/v1 \
  --api-key-env LOCAL_API_KEY \
  --model qwen \
  setup
```

Then run:

```bash
export LOCAL_API_KEY="..."
tau --provider local
```

## Shell Completion

Shell completion is not enabled yet. The Typer application is currently created
with completion disabled so the command surface can stay stable while Tau is
still moving through the roadmap.
