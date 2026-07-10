# Tasks: Greeting Extension

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~30–50 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | single-pr |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

---

## Context

The extension infrastructure is fully wired:
- `get_default_registry().get_tools()` feeds into `create_coding_tools()` (session.py:288)
- `get_default_registry().get_commands()` auto-registers slash commands in `create_default_command_registry()` (commands.py:372–381)
- Extension files placed in `~/.tau/extensions/*.py` or `.tau/extensions/*.py` are auto-discovered

This task only needs to create the extension file and add tests. No changes to core extension infrastructure are required.

**Spec**: A `@tool("hello")` that greets the user and a `@command("hi")` slash command.
**Design**: Follow the existing pattern in `example_extensions/hello_ext.py`.

---

## Task 1 — Create the greeting extension file

**File**: `example_extensions/greeting_ext.py` (new)

**Acceptance criteria**:
- Extends `Extension` from `tau_coding.extensions`
- Registers a `@tool("hello", "Greet the user")` that returns a greeting string
- Registers a `@command("hi", description="Say hi")` that returns a greeting from args
- Follows the same class/module structure as `example_extensions/hello_ext.py`
- No syntax errors, passes `ruff` and `mypy`

**Details**:
- The `@tool("hello")` method should accept an optional `name: str = "world"` parameter and return `f"Hello, {name}!"`
- The `@command("hi")` method should accept `args: str` and return a greeting using args or a default
- Keep it simple: one class, two decorated methods, no event handlers needed

**Verification**: `uv run python -c "from tau_coding.extensions import ExtensionRegistry; r = ExtensionRegistry(); r.add_search_path('example_extensions'); r.load_all(); assert any(t.name == 'hello' for t in r.get_tools()); print('OK')"`

---

## Task 2 — Add tests for the greeting extension

**File**: `tests/test_extensions.py` (append) or `tests/test_greeting_ext.py` (new)

**Acceptance criteria**:
- Tests load the extension from `example_extensions/greeting_ext.py` via `ExtensionRegistry`
- Verifies `@tool("hello")` is registered with correct name and description
- Verifies `@command("hi")` is registered with correct name and description
- Verifies the tool executor returns the expected greeting string
- All existing tests still pass

**Test structure** (add to existing `test_extensions.py` or a new test module):

```python
def test_greeting_extension_loads() -> None:
    """Greeting extension is discoverable and loads correctly."""
    reg = ExtensionRegistry()
    reg.add_search_path(Path("example_extensions"))
    instances = reg.load_all()
    greeting_exts = [i for i in instances if "greeting" in i.path.lower()]
    assert len(greeting_exts) == 1
    ext = greeting_exts[0]
    tool_names = [t.name for t in ext.tools]
    cmd_names = [c.name for c in ext.commands]
    assert "hello" in tool_names
    assert "hi" in cmd_names


def test_greeting_tool_returns_greeting() -> None:
    """@tool('hello') returns a greeting string when called."""
    from tau_coding.extensions import Extension, tool

    class TestGreetingExt(Extension):
        @tool("hello", "Greet the user")
        def hello(self, name: str = "world") -> str:
            return f"Hello, {name}!"

    ext = TestGreetingExt()
    assert ext.hello() == "Hello, world!"
    assert ext.hello("Tau") == "Hello, Tau!"
```

**Verification**: `uv run pytest tests/test_extensions.py -v`

---

## Task 3 — Final verification

**Acceptance criteria**:
- `ruff` passes on new/changed files: `uv run ruff check example_extensions/greeting_ext.py tests/`
- `mypy` passes on new/changed files: `uv run mypy example_extensions/greeting_ext.py`
- All tests pass: `uv run pytest tests/ -v`

---

## Notes

- No changes to `src/tau_coding/extensions.py`, `src/tau_coding/tools.py`, `src/tau_coding/commands.py`, or `src/tau_coding/session.py` are needed — the extension system already auto-discovers and registers tools + commands.
- To *use* the extension at runtime, users copy it to `~/.tau/extensions/greeting_ext.py`. The `example_extensions/` location is for reference and testing only.
