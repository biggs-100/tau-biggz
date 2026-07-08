---
name: skill-creator
description: "Trigger: create skill, new skill, crear skill, make extension, new extension, crear extension, make harness, new harness, custom harness, crear harness. Creates Tau skills, extensions, or harnesses after exploring project context, Tau architecture, and relevant references."
---

## Activation Contract

Use this workflow when the user asks to **create a new skill, extension, or harness** for Tau.

Tau has three artifact types you can create:

| Artifact | Format | Location | Purpose |
|----------|--------|----------|---------|
| **Skill** | `.md` with frontmatter | `.tau/skills/<name>/SKILL.md` or `~/.tau/skills/<name>/SKILL.md` | Markdown instructions the agent loads via `/skill:<name>` |
| **Extension** | `.py` (extension class) | `.tau/extensions/<name>.py` or `~/.tau/extensions/<name>.py` | Python code with `@tool`, `@command`, `@on` decorators |
| **Harness** | `.toml` | `.tau/harnesses/<name>.toml` or `~/.tau/harnesses/<name>.toml` | TOML config for personality, tools, approval, subagents |

## Hard Rules

1. **ALWAYS explore before creating** — never jump to implementation without context.
2. Follow the exploration order: project → Tau architecture → web references.
3. After exploring, present a plan to the user before writing files.
4. Reference existing examples when creating new artifacts.
5. Validate syntax after creation (ruff for .py, tomllib for .toml, frontmatter parse for .md).

## Exploration Phase (MANDATORY)

### Step 1 — Explore the project

Read project context to understand naming, conventions, and existing patterns:

- `AGENTS.md` or project README for guidelines
- Existing skills (`ls .tau/skills/`, `ls ~/.tau/skills/`)
- Existing extensions (`ls .tau/extensions/`, `ls ~/.tau/extensions/`, `ls example_extensions/`)
- Existing harnesses (`ls .tau/harnesses/`, `ls ~/.tau/harnesses/`)
- `pyproject.toml` for project metadata

### Step 2 — Explore Tau's architecture

Read the relevant source files to understand the API:

**For skills**:
- `src/tau_coding/skills.py` — Skill dataclass, load/expand/format
- `src/tau_coding/resources.py` — `parse_markdown_resource()` for frontmatter format

**For extensions**:
- `src/tau_coding/extensions.py` — Extension base class, @tool/@command/@on decorators
- `src/tau_coding/tools.py` — `_wrap_tool_with_events()` for event dispatch
- Existing examples in `example_extensions/`

**For harnesses**:
- `src/tau_coding/harness.py` — HarnessDefinition, _parse_harness_file()
- `dev-notes/harnesses.md` — full harness guide
- Existing examples in `.tau/harnesses/` or `~/.tau/harnesses/`

### Step 3 — Search the web (when relevant)

When the skill, extension, or harness wraps or integrates an external service, search for:
- API documentation
- Best practices
- Python client libraries
- Security considerations

## Execution Steps

### Creating a Skill

1. Choose a kebab-case name that matches the user-facing trigger.
2. Create `.tau/skills/<name>/SKILL.md` (project) or `~/.tau/skills/<name>/SKILL.md` (user):

```markdown
---
name: <skill-name>
description: "Trigger: {trigger phrases}. {One-line summary}."
---

## Activation Contract

When to use this skill...

## Hard Rules

Non-negotiable constraints...

## Execution Steps

1. First step...
2. Second step...

## Output Contract

What this skill produces.
```

3. Frontmatter rules:
   - `name` matches the directory name
   - `description` is one line with trigger words first
   - Only simple `key: value` pairs (Tau's parser is minimal)
4. Verify: create a test invocation with `python -c "from tau_coding.skills import load_skills; skills = load_skills(); assert any(s.name == '<name>' for s in skills)"`

### Creating an Extension

1. Choose a PascalCase class name and a kebab-case file name.
2. Create `.tau/extensions/<name>.py` (project) or `~/.tau/extensions/<name>.py` (user):

```python
"""Docstring describing the extension."""

from tau_coding.extensions import Extension, tool, command, on


class <Name>Extension(Extension):
    @tool("<tool_name>", "<Tool description>")
    def <method_name>(self, <params>) -> <return_type>:
        \"\"\"Docstring.\"\"\"
        ...

    @command("<cmd_name>", description="<description>")
    def <method_name>(self, args: str) -> str | None:
        ...
        return ...

    @on("<event_name>")
    def <method_name>(self, event: dict) -> dict | None:
        ...
        return None  # or {"block": True, "reason": "..."}
```

3. Follow the existing patterns in `example_extensions/hello_ext.py` and `example_extensions/greeting_ext.py`.
4. Verify: `uv run ruff check .tau/extensions/<name>.py` and test loading with:

```python
from tau_coding.extensions import ExtensionRegistry
from pathlib import Path
reg = ExtensionRegistry()
reg.add_search_path(Path(".tau/extensions"))
instances = reg.load_all()
assert any("<name>" in i.path for i in instances)
```

### Creating a Harness

1. Choose a short name (one word, kebab-case).
2. Create `.tau/harnesses/<name>.toml` (project) or `~/.tau/harnesses/<name>.toml` (user):

```toml
name = "<name>"
description = "<One-line description>"

[personality]
system_prompt = "You are..."

[tools]
builtin = ["read", "write", "edit", "bash"]

[approval]
default = "allow"

[approval.rules]
bash = "deny"

[[subagents]]
name = "<agent-name>"
instructions = "<agent instructions>"
tools = ["read"]
```

3. Supported sections: `name`, `description`, `[personality]` (system_prompt, guidelines), `[provider]` (name, model, thinking), `[tools]` (builtin, extensions), `[approval]` (default, rules), `[[subagents]]` (name, instructions, tools).
4. Verify: `python -c "from tau_coding.harness import load_harness; h = load_harness('<name>'); print(f'OK: {h.name}')"` and `python -c "import tomllib; tomllib.loads(open('.tau/harnesses/<name>.toml').read()); print('TOML OK')"`

## Output Contract

After completing, report:
- What was created (skill/extension/harness) and its path
- Key sections or decorators used
- Verification results (parsing, loading, syntax checks)
- How to invoke/use it (`/skill:<name>`, runs automatically, `tau --harness <name>`)
