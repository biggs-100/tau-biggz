# Configuration and Files

Tau keeps durable application state in the user's home directory and reads
project-local instructions from the active working directory.

## Tau Home

The default Tau home is:

```text
~/.tau/
```

Important files and directories:

```text
~/.tau/providers.json
~/.tau/sessions/
~/.tau/skills/
~/.tau/prompts/
~/.tau/AGENTS.md
```

Tau also reads user-level `.agents` resources:

```text
~/.agents/skills/
~/.agents/prompts/
~/.agents/AGENTS.md
```

## Provider Settings

Provider metadata is stored in:

```text
~/.tau/providers.json
```

Example:

```json
{
  "default_provider": "local",
  "providers": [
    {
      "name": "local",
      "type": "openai-compatible",
      "base_url": "http://localhost:11434/v1",
      "api_key_env": "LOCAL_API_KEY",
      "models": ["qwen", "llama"],
      "default_model": "qwen"
    }
  ]
}
```

API keys are not written to this file. Each provider entry names the environment
variable that should contain its API key.

Useful commands:

```bash
tau providers
tau --provider local --model qwen setup
```

Inside the TUI:

```text
/provider
/provider local
/model
/model qwen
```

## Sessions

Tau indexes sessions under:

```text
~/.tau/sessions/
```

Session transcripts are append-only JSONL files. They preserve messages, model
changes, and the active leaf in the session tree.

Useful commands:

```bash
tau sessions
tau --resume <session-id>
tau --new-session
```

Inside the TUI:

```text
/sessions
/status
```

## Skills and Prompt Templates

Tau loads markdown skills from these locations in increasing precedence order:

```text
~/.tau/skills/
~/.agents/skills/
~/.agents/
<cwd>/.tau/skills/
<cwd>/.agents/skills/
<cwd>/.agents/
```

Prompt templates are loaded from:

```text
~/.tau/prompts/
~/.agents/prompts/
<cwd>/.tau/prompts/
<cwd>/.agents/prompts/
```

Project resources override user resources with the same name. Duplicate or
overridden resources are reported through diagnostics instead of preventing Tau
from starting.

Useful TUI commands:

```text
/skills
/resources
/skill:<name> [request]
```

## Project Context

Tau discovers instruction files and includes them in the generated system
prompt. The current discovery order is:

```text
~/.tau/AGENTS.md
~/.agents/AGENTS.md
<project root>/AGENTS.md
<project root>/.../<cwd>/AGENTS.md
<cwd>/.tau/AGENTS.md
<cwd>/.agents/AGENTS.md
```

The project root is the nearest ancestor containing a marker such as `.git`,
`pyproject.toml`, `uv.lock`, `setup.py`, or `package.json`.

Useful TUI commands:

```text
/context
/reload
```
