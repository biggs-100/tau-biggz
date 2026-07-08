# Harness System

A harness defines the personality, tools, and behavior of a Tau session.
Each project can have its own harness in ``.tau/harness.toml``.

## Quick start

Create `.tau/harness.toml` in your project:

```toml
name = "legal"
description = "Corporate law assistant"

[personality]
system_prompt = """
You are a corporate law assistant.
Help with contract review, legal research, and document drafting.
Maintain a formal and precise tone.
"""

[tools]
builtin = ["read", "write"]
```

Run Tau from that directory:

```bash
tau   # auto-detects .tau/harness.toml
```

## Resolution order

```
1. .tau/harnesses/<name>.toml    explicit harness name
2. .tau/harness.toml             default project harness
3. ~/.tau/harnesses/<name>.toml  global (optional)
4. coding (built-in)             implicit fallback
```

## CLI flags

```bash
tau --harness legal              # use a specific harness
tau --list-harnesses             # list all available
```

## Schema reference

```toml
name = "my-harness"              # required: unique identifier
description = "What it does"     # optional: human-readable

[personality]
system_prompt = "..."            # replaces the default coding prompt
guidelines = []                  # additional behavioral rules (future)

[provider]
name = "opencode-zen"            # provider to use (optional, uses default if unset)
model = "gpt-5.5"                # model to use (optional)
thinking = "medium"              # thinking level (optional)

[tools]
builtin = ["read", "write"]      # which built-in tools to enable
                                 # default: all (read, write, edit, bash)
                                 # set empty to use only extension tools
extensions = []                  # extension tool names (future)
```

## How it works

1. At CLI startup, ``load_harness()`` resolves the harness TOML file
2. ``set_active_harness()`` stores it globally
3. Session init calls ``_harness_filtered_tools()`` — only allows tools
   listed in ``tools.builtin`` (or all if unset)
4. Session init calls ``_harness_system_prompt()`` — uses the harness
   ``personality.system_prompt`` instead of the default coding prompt
   (unless a ``custom_system_prompt`` was set programmatically)

## Global harnesses

Put reusable harnesses in ``~/.tau/harnesses/`` for use across projects:

```bash
~/.tau/harnesses/
  legal.toml
  accounting.toml
  review.toml
```

These are optional. The default installation has no global harnesses.

## Built-in "coding" harness

When no harness file is found, Tau uses an implicit ``coding`` harness
that behaves like the traditional coding agent (all tools, default prompt).
No file needs to exist for this.

## Architecture

- ``src/tau_coding/harness.py`` — HarnessDefinition, loader, resolver
- ``src/tau_coding/cli.py`` — ``--harness`` and ``--list-harnesses`` flags
- ``src/tau_coding/session.py`` — ``_harness_filtered_tools()``,
  ``_harness_system_prompt()``
