from __future__ import annotations

import asyncio
import shlex
import struct
import sys
import zlib
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

import pytest

from tau_agent import AgentEndEvent, ErrorEvent
from tau_coding import (
    create_bash_tool,
    create_coding_tools,
    create_edit_tool,
    create_edit_tool_definition,
    create_read_tool,
    create_read_tool_definition,
    create_write_tool,
)
from tau_coding.agents import AgentDef
from tau_coding.tools import create_subagent_tool, create_web_search_tool
from tau_agent.messages import TextContent


def _text(r):
    return "".join(b.text for b in r.content if isinstance(b, TextContent))


from tau_coding.tools_types import ToolInputError


class FakeCancellationToken:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def is_cancelled(self) -> bool:
        return self.cancelled


@pytest.mark.anyio
async def test_create_coding_tools_returns_initial_tool_set(tmp_path: Path) -> None:
    tools = create_coding_tools(cwd=tmp_path)

    assert [tool.name for tool in tools] == [
        "read",
        "write",
        "edit",
        "bash",
        "web_search",
        "subagent_run",
    ]
    edit_tool = tools[2]
    assert edit_tool.prompt_snippet is not None
    assert "Use edit for precise changes" in edit_tool.prompt_guidelines[0]


def test_tool_definitions_expose_pi_style_prompt_metadata(tmp_path: Path) -> None:
    definition = create_edit_tool_definition(cwd=tmp_path)

    assert definition.prompt_snippet.startswith("Make precise file edits")
    assert len(definition.prompt_guidelines) == 4


def test_read_tool_schema_defines_line_controls_as_integers(tmp_path: Path) -> None:
    definition = create_read_tool_definition(cwd=tmp_path)
    properties = definition.input_schema["properties"]

    assert isinstance(properties, dict)
    assert properties["offset"]["type"] == "integer"
    assert properties["limit"]["type"] == "integer"


@pytest.mark.anyio
async def test_read_tool_reads_file_with_offset_and_limit(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("one\ntwo\nthree\n")
    tool = create_read_tool(cwd=tmp_path)

    result = await tool.execute({"path": "notes.txt", "offset": 2, "limit": 1})

    assert _text(result) == "two\n\n[2 more lines in file. Use offset=3 to continue.]"
    assert result.details is not None
    assert result.details["path"] == str(path)
    assert isinstance(result.details["truncation"], dict)


@pytest.mark.anyio
async def test_read_tool_treats_zero_offset_as_start_of_file(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("one\ntwo\nthree\n")
    tool = create_read_tool(cwd=tmp_path)

    result = await tool.execute({"path": "notes.txt", "offset": 0, "limit": 1})

    assert _text(result) == "one\n\n[3 more lines in file. Use offset=2 to continue.]"


@pytest.mark.anyio
async def test_write_tool_creates_parent_directories(tmp_path: Path) -> None:
    tool = create_write_tool(cwd=tmp_path)

    result = await tool.execute({"path": "nested/file.txt", "content": "hello"})

    assert (tmp_path / "nested" / "file.txt").read_text() == "hello"


@pytest.mark.anyio
async def test_edit_tool_applies_multiple_exact_replacements(tmp_path: Path) -> None:
    path = tmp_path / "file.txt"
    path.write_text("alpha\nbeta\ngamma\n")
    tool = create_edit_tool(cwd=tmp_path)

    result = await tool.execute(
        {
            "path": "file.txt",
            "edits": [
                {"oldText": "alpha", "newText": "one"},
                {"oldText": "gamma", "newText": "three"},
            ],
        }
    )

    assert path.read_text() == "one\nbeta\nthree\n"


@pytest.mark.anyio
async def test_edit_tool_rolls_back_when_any_edit_fails(tmp_path: Path) -> None:
    path = tmp_path / "file.txt"
    original = "alpha\nbeta\ngamma\n"
    path.write_text(original)
    tool = create_edit_tool(cwd=tmp_path)

    with pytest.raises(ValueError, match="Could not find edits\\[1\\]"):
        await tool.execute(
            {
                "path": "file.txt",
                "edits": [
                    {"oldText": "alpha", "newText": "one"},
                    {"oldText": "missing", "newText": "nope"},
                ],
            }
        )

    assert path.read_text() == original


@pytest.mark.anyio
async def test_edit_tool_requires_unique_matches(tmp_path: Path) -> None:
    path = tmp_path / "file.txt"
    path.write_text("repeat\nrepeat\n")
    tool = create_edit_tool(cwd=tmp_path)

    with pytest.raises(ValueError, match="Found 2 occurrences"):
        await tool.execute(
            {
                "path": "file.txt",
                "edits": [{"oldText": "repeat", "newText": "once"}],
            }
        )


@pytest.mark.anyio
async def test_bash_tool_captures_stdout_and_exit_code(tmp_path: Path) -> None:
    tool = create_bash_tool(cwd=tmp_path)

    result = await tool.execute({"command": "printf hello"})

    assert _text(result) == "hello"
    assert result.details is not None
    assert result.details["exit_code"] == 0
    assert result.details["timed_out"] is False


@pytest.mark.anyio
@pytest.mark.skipif(sys.platform == "win32", reason="bash-specific shell prefix test")
async def test_create_coding_tools_applies_shell_command_prefix(
    tmp_path: Path,
) -> None:
    tools = create_coding_tools(
        cwd=tmp_path,
        shell_command_prefix="shopt -s expand_aliases\nalias greet='printf coding-tool-alias'",
    )
    bash_tool = next(tool for tool in tools if tool.name == "bash")

    result = await bash_tool.execute({"command": "greet"})

    assert _text(result) == "coding-tool-alias"
    assert result.details is not None
    assert result.details["shell_command_prefix_applied"] is True


@pytest.mark.anyio
@pytest.mark.skipif(sys.platform == "win32", reason="bash-specific shell prefix test")
async def test_bash_tool_applies_opt_in_shell_command_prefix(tmp_path: Path) -> None:
    rc_path = tmp_path / ".zshrc"
    marker = tmp_path / "sourced"
    rc_path.write_text(
        f"alias greet='printf alias-output'\ntouch {shlex.quote(str(marker))}\n",
        encoding="utf-8",
    )
    prefix = f"shopt -s expand_aliases\neval \"$(grep '^alias ' {shlex.quote(str(rc_path))})\""
    tool = create_bash_tool(cwd=tmp_path, shell_command_prefix=prefix)

    result = await tool.execute({"command": "greet"})

    assert _text(result) == "alias-output"
    assert result.details is not None
    assert result.details["shell_command_prefix_applied"] is True
    assert not marker.exists()


@pytest.mark.anyio
async def test_bash_tool_reports_timeout(tmp_path: Path) -> None:
    tool = create_bash_tool(cwd=tmp_path)

    result = await tool.execute({"command": "sleep 1", "timeout": 0.01})

    assert result.details is not None
    assert result.details["timed_out"] is True
    assert "timed out" in _text(result)


@pytest.mark.anyio
async def test_bash_tool_timeout_kills_shell_children(tmp_path: Path) -> None:
    tool = create_bash_tool(cwd=tmp_path)
    marker = tmp_path / "marker"

    start = monotonic()
    result = await tool.execute({"command": "(sleep 0.25; touch marker) & wait", "timeout": 0.01})
    duration = monotonic() - start
    await asyncio.sleep(0.35)

    assert result.details is not None
    assert result.details["timed_out"] is True
    assert duration < 1.5
    assert not marker.exists()


@pytest.mark.anyio
async def test_bash_tool_cancellation_kills_shell_children(tmp_path: Path) -> None:
    tool = create_bash_tool(cwd=tmp_path)
    token = FakeCancellationToken()

    task = asyncio.create_task(tool.execute({"command": "sleep 1 & wait"}, signal=token))
    await asyncio.sleep(0.05)
    token.cancel()
    start = monotonic()
    result = await task
    duration = monotonic() - start

    assert result.details is not None
    assert result.details["cancelled"] is True
    assert "cancelled" in _text(result)
    assert duration < 1.5


# ── read tool edge cases ────────────────────────────────────────────


@pytest.mark.anyio
async def test_read_tool_negative_offset_raises(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_text("hello\n")
    tool = create_read_tool(cwd=tmp_path)
    with pytest.raises(ToolInputError, match="offset must be at least 0"):
        await tool.execute({"path": "f.txt", "offset": -1})


@pytest.mark.anyio
async def test_read_tool_limit_less_than_one_raises(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_text("hello\n")
    tool = create_read_tool(cwd=tmp_path)
    with pytest.raises(ToolInputError, match="limit must be at least 1"):
        await tool.execute({"path": "f.txt", "limit": 0})


@pytest.mark.anyio
async def test_read_tool_directory_raises(tmp_path: Path) -> None:
    tool = create_read_tool(cwd=tmp_path)
    with pytest.raises(ToolInputError, match="Path is a directory"):
        await tool.execute({"path": "."})


@pytest.mark.anyio
async def test_read_tool_missing_file_raises(tmp_path: Path) -> None:
    tool = create_read_tool(cwd=tmp_path)
    with pytest.raises(ToolInputError, match="File not found"):
        await tool.execute({"path": "nonexistent.txt"})


def _minimal_png_bytes() -> bytes:
    """Create a minimal valid 1x1 red PNG (68 bytes)."""

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = _chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


@pytest.mark.anyio
async def test_read_tool_image_file_returns_base64(tmp_path: Path) -> None:
    img_path = tmp_path / "test.png"
    img_path.write_bytes(_minimal_png_bytes())
    tool = create_read_tool(cwd=tmp_path)
    result = await tool.execute({"path": "test.png"})
    assert result.details is not None
    assert result.details["mime_type"] == "image/png"
    assert result.details["bytes"] > 0
    assert "image_base64" in result.details
    assert isinstance(result.details["image_base64"], str)
    assert len(result.details["image_base64"]) > 0


@pytest.mark.anyio
async def test_read_tool_offset_beyond_end_raises(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_text("one\ntwo\n")
    tool = create_read_tool(cwd=tmp_path)
    with pytest.raises(ToolInputError, match="beyond end of file"):
        await tool.execute({"path": "f.txt", "offset": 10})


@pytest.mark.anyio
async def test_read_tool_first_line_exceeds_limit(tmp_path: Path) -> None:
    """First line > 50 KB triggers the sed hint message."""
    path = tmp_path / "big.txt"
    path.write_text("x" * 60_000 + "\nrest\n")
    tool = create_read_tool(cwd=tmp_path)
    result = await tool.execute({"path": "big.txt"})
    assert "exceeds" in _text(result)
    assert "sed" in _text(result)
    assert "50.0KB" in _text(result)


# ── edit tool edge cases ────────────────────────────────────────────


@pytest.mark.anyio
async def test_edit_tool_missing_file_raises(tmp_path: Path) -> None:
    tool = create_edit_tool(cwd=tmp_path)
    with pytest.raises(ToolInputError, match="File not found"):
        await tool.execute({"path": "nonexistent.txt", "edits": [{"oldText": "a", "newText": "b"}]})


@pytest.mark.anyio
async def test_edit_tool_directory_raises(tmp_path: Path) -> None:
    tool = create_edit_tool(cwd=tmp_path)
    with pytest.raises(ToolInputError, match="Path is a directory"):
        await tool.execute({"path": ".", "edits": [{"oldText": "a", "newText": "b"}]})


# ── bash tool edge cases ────────────────────────────────────────────


@pytest.mark.anyio
async def test_bash_tool_timeout_zero_raises(tmp_path: Path) -> None:
    tool = create_bash_tool(cwd=tmp_path)
    with pytest.raises(ToolInputError, match="timeout must be greater than 0"):
        await tool.execute({"command": "echo hi", "timeout": 0})


@pytest.mark.anyio
async def test_bash_tool_timeout_negative_raises(tmp_path: Path) -> None:
    tool = create_bash_tool(cwd=tmp_path)
    with pytest.raises(ToolInputError, match="timeout must be greater than 0"):
        await tool.execute({"command": "echo hi", "timeout": -1})


@pytest.mark.anyio
async def test_bash_tool_precancelled_raises(tmp_path: Path) -> None:
    tool = create_bash_tool(cwd=tmp_path)
    token = FakeCancellationToken()
    token.cancel()
    with pytest.raises(ToolInputError, match="Command cancelled"):
        await tool.execute({"command": "echo hi"}, signal=token)


@pytest.mark.anyio
async def test_bash_tool_exit_code_reported(tmp_path: Path) -> None:
    tool = create_bash_tool(cwd=tmp_path)
    result = await tool.execute({"command": 'python -c "exit(42)"'})
    assert result.details is not None
    assert result.details["exit_code"] == 42
    assert "exited with code 42" in _text(result)


# ── web_search tool tests ───────────────────────────────────────────


class _MockResponse:
    """Fake httpx response used by mock clients below."""

    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        pass


class _NoResultsClient:
    """Mock httpx.AsyncClient returning an empty result page."""

    def __init__(self, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> _NoResultsClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def post(self, url: str, **kwargs: object) -> _MockResponse:
        return _MockResponse("<html><body>nothing</body></html>")


class _ResultsClient:
    """Mock httpx.AsyncClient returning search-result HTML."""

    HTML = (
        "<html>"
        '<a class="result__a" href="https://example.com"><h2>Example Title</h2>'
        '<a class="result__a" href="https://test.org"><h3>Test Site</h3>'
        "</html>"
    )

    def __init__(self, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> _ResultsClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def post(self, url: str, **kwargs: object) -> _MockResponse:
        return _MockResponse(self.HTML)


class _ErrorClient:
    """Mock httpx.AsyncClient that raises on post."""

    def __init__(self, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> _ErrorClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def post(self, url: str, **kwargs: object) -> _MockResponse:
        raise RuntimeError("Connection failed unexpectedly")


@pytest.mark.anyio
async def test_web_search_empty_query_returns_error() -> None:
    tool = create_web_search_tool()
    result = await tool.execute({"query": ""})
    assert "No search query" in _text(result)


@pytest.mark.anyio
async def test_web_search_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("httpx.AsyncClient", _NoResultsClient)
    tool = create_web_search_tool()
    result = await tool.execute({"query": "something"})
    assert _text(result) == "No results found."


@pytest.mark.anyio
async def test_web_search_returns_formatted_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("httpx.AsyncClient", _ResultsClient)
    tool = create_web_search_tool()
    result = await tool.execute({"query": "test"})
    assert "Example Title" in _text(result)
    assert "https://example.com" in _text(result)
    assert "Test Site" in _text(result)
    assert "https://test.org" in _text(result)


@pytest.mark.anyio
async def test_web_search_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("httpx.AsyncClient", _ErrorClient)
    tool = create_web_search_tool()
    result = await tool.execute({"query": "test"})
    assert "Search failed" in _text(result)
    assert "Connection failed unexpectedly" in _text(result)


# ── subagent tool tests ─────────────────────────────────────────────


class _ContentEndEvent(AgentEndEvent):
    """AgentEndEvent with a assistant message so the subagent can extract it."""

    def __init__(self, content: str = "", **kwargs: object) -> None:
        from tau_agent.messages import AssistantMessage, TextContent
        super().__init__(
            messages=[AssistantMessage(content=[TextContent(text=content)])],
            **kwargs,
        )


class _MockProvider:
    """Fake provider whose only job is to support await provider.aclose()."""

    async def aclose(self) -> None:
        pass


class _MockHarness:
    """Fake AgentHarness that yields a single content-bearing end event."""

    def __init__(self, config: object) -> None:
        self.config = config

    async def prompt(self, task: str) -> object:  # type: ignore[misc]
        yield _ContentEndEvent(content="Hello from sub-agent!")


class _RecordingHarness:
    """Fake AgentHarness that records config and yields a success event."""

    instances: list[object] = []

    def __init__(self, config: object) -> None:
        self.instances.append(config)
        self.config = config

    async def prompt(self, task: str) -> object:  # type: ignore[misc]
        yield _ContentEndEvent(content="done")


class _ErrorHarness:
    """Fake AgentHarness that yields an unrecoverable ErrorEvent."""

    def __init__(self, config: object) -> None:
        self.config = config

    async def prompt(self, task: str) -> object:  # type: ignore[misc]
        yield ErrorEvent(message="Something broke", recoverable=False)


@pytest.mark.anyio
async def test_subagent_empty_task_returns_error() -> None:
    tool = create_subagent_tool()
    result = await tool.execute({"task": ""})
    assert "No task provided" in _text(result)


@pytest.mark.anyio
async def test_subagent_no_provider_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tau_coding.provider_config.load_provider_settings",
        lambda: SimpleNamespace(providers=()),
    )
    tool = create_subagent_tool()
    result = await tool.execute({"task": "do work"})
    assert "No provider configured" in _text(result)


@pytest.mark.anyio
async def test_subagent_success_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_provider_cfg = SimpleNamespace(
        default_model="test-model",
        name="test",
        models=("test-model",),
    )
    monkeypatch.setattr(
        "tau_coding.provider_config.load_provider_settings",
        lambda: SimpleNamespace(
            providers=(mock_provider_cfg,),
            default_provider="test",
        ),
    )
    monkeypatch.setattr(
        "tau_coding.provider_runtime.create_model_provider",
        lambda *a, **kw: _MockProvider(),
    )
    monkeypatch.setattr("tau_agent.AgentHarness", _MockHarness)

    tool = create_subagent_tool()
    result = await tool.execute({"task": "do work"})
    assert _text(result) == "Hello from sub-agent!"


@pytest.mark.anyio
async def test_subagent_with_agent_file_overrides_system_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ad = AgentDef(
        name="helper",
        description="Helper agent",
        system_prompt="You are a helpful assistant.",
    )
    monkeypatch.setattr("tau_coding.agents.load_agent", lambda _name: ad)

    mock_provider_cfg = SimpleNamespace(
        default_model="test-model",
        name="test",
        models=("test-model",),
    )
    monkeypatch.setattr(
        "tau_coding.provider_config.load_provider_settings",
        lambda: SimpleNamespace(
            providers=(mock_provider_cfg,),
            default_provider="test",
        ),
    )
    monkeypatch.setattr(
        "tau_coding.provider_runtime.create_model_provider",
        lambda *a, **kw: _MockProvider(),
    )

    _RecordingHarness.instances.clear()
    monkeypatch.setattr("tau_agent.AgentHarness", _RecordingHarness)

    tool = create_subagent_tool()
    result = await tool.execute({"task": "do work", "agent": "helper"})
    assert len(_RecordingHarness.instances) == 1
    system = getattr(_RecordingHarness.instances[0], "system", "")
    assert "helpful assistant" in system


@pytest.mark.anyio
async def test_subagent_instructions_override_agent_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ad = AgentDef(
        name="helper",
        description="Helper agent",
        system_prompt="You are a helpful assistant.",
    )
    monkeypatch.setattr("tau_coding.agents.load_agent", lambda _name: ad)

    mock_provider_cfg = SimpleNamespace(
        default_model="test-model",
        name="test",
        models=("test-model",),
    )
    monkeypatch.setattr(
        "tau_coding.provider_config.load_provider_settings",
        lambda: SimpleNamespace(
            providers=(mock_provider_cfg,),
            default_provider="test",
        ),
    )
    monkeypatch.setattr(
        "tau_coding.provider_runtime.create_model_provider",
        lambda *a, **kw: _MockProvider(),
    )

    _RecordingHarness.instances.clear()
    monkeypatch.setattr("tau_agent.AgentHarness", _RecordingHarness)

    tool = create_subagent_tool()
    result = await tool.execute({"task": "do work", "agent": "helper", "instructions": "Be brief."})
    assert len(_RecordingHarness.instances) == 1
    system = getattr(_RecordingHarness.instances[0], "system", "")
    # instructions must override the agent file's system_prompt
    assert "Be brief." in system
    assert "helpful assistant" not in system


@pytest.mark.anyio
async def test_subagent_error_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_provider_cfg = SimpleNamespace(
        default_model="test-model",
        name="test",
        models=("test-model",),
    )
    monkeypatch.setattr(
        "tau_coding.provider_config.load_provider_settings",
        lambda: SimpleNamespace(
            providers=(mock_provider_cfg,),
            default_provider="test",
        ),
    )
    monkeypatch.setattr(
        "tau_coding.provider_runtime.create_model_provider",
        lambda *a, **kw: _MockProvider(),
    )
    monkeypatch.setattr("tau_agent.AgentHarness", _ErrorHarness)

    tool = create_subagent_tool()
    result = await tool.execute({"task": "do work"})
    assert "Sub-agent error" in _text(result)
    assert "Something broke" in _text(result)


@pytest.mark.anyio
async def test_subagent_top_level_exception_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """load_provider_settings raises → outer except catches it."""
    monkeypatch.setattr(
        "tau_coding.provider_config.load_provider_settings",
        lambda: (_ for _ in ()).throw(RuntimeError("Boom!")),  # raise on call
    )
    tool = create_subagent_tool()
    result = await tool.execute({"task": "do work"})
    assert "Sub-agent failed" in _text(result)
    assert "Boom" in _text(result)


# ── web_search: max-eighth-results branch ───────────────────────────


class _EightPlusResultsClient:
    """Mock client returning HTML with 10 search results."""

    HTML = (
        "<html>"
        + "".join(
            f'<a class="result__a" href="https://site{i}.com"><h2>Result {i}</h2>'
            for i in range(10)
        )
        + "</html>"
    )

    def __init__(self, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> _EightPlusResultsClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def post(self, url: str, **kwargs: object) -> _MockResponse:
        return _MockResponse(self.HTML)


@pytest.mark.anyio
async def test_web_search_limits_to_eight_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("httpx.AsyncClient", _EightPlusResultsClient)
    tool = create_web_search_tool()
    result = await tool.execute({"query": "test"})
    # Should contain exactly 8 results, not 10
    assert _text(result).count("Result ") == 8
    assert "Result 0" in _text(result)
    assert "Result 7" in _text(result)
    assert "Result 8" not in _text(result)
    assert "Result 9" not in _text(result)


# ── read tool: remaining branches ───────────────────────────────────


@pytest.mark.anyio
async def test_read_tool_no_offset_limit_small_file(tmp_path: Path) -> None:
    """Small file with no offset/limit hits the else branch (line 239)."""
    path = tmp_path / "small.txt"
    path.write_text("hello\nworld\n")
    tool = create_read_tool(cwd=tmp_path)
    result = await tool.execute({"path": "small.txt"})
    # The trailing newline is preserved from the file content
    assert _text(result) == "hello\nworld\n"


@pytest.mark.anyio
async def test_read_tool_truncation_by_lines(tmp_path: Path) -> None:
    """File with >2000 lines triggers line-count truncation."""
    path = tmp_path / "manylines.txt"
    path.write_text("\n".join(f"line{i}" for i in range(2010)))
    tool = create_read_tool(cwd=tmp_path)
    result = await tool.execute({"path": "manylines.txt"})
    assert "Showing lines" in _text(result)
    assert "Use offset=" in _text(result)
    assert "2010" in _text(result)  # total lines mentioned


@pytest.mark.anyio
async def test_read_tool_truncation_by_bytes(tmp_path: Path) -> None:
    """File where total content exceeds 50KB but lines <= 2000 triggers byte truncation."""
    path = tmp_path / "bigfile.txt"
    # 1800 lines of 30 chars each = ~55KB — exceeds 50KB limit
    path.write_text("\n".join("x" * 30 for _ in range(1800)))
    tool = create_read_tool(cwd=tmp_path)
    result = await tool.execute({"path": "bigfile.txt"})
    assert "Showing lines" in _text(result)
    assert "limit)" in _text(result) or "50.0KB" in _text(result)


# ── bash tool: truncation messages ─────────────────────────────────


@pytest.mark.anyio
async def test_bash_tool_truncation_line_count(tmp_path: Path) -> None:
    """Bash output > 2000 lines triggers line-count truncation message."""
    tool = create_bash_tool(cwd=tmp_path)
    result = await tool.execute({"command": 'python -c "for i in range(2100): print(i)"'})
    assert result.details is not None
    trunc = result.details["truncation"]
    assert trunc["truncated"] is True
    assert trunc["total_lines"] > 2000
    assert "Full output:" in _text(result)


@pytest.mark.anyio
async def test_bash_tool_truncation_last_line_partial(tmp_path: Path) -> None:
    """Single large output line > 50KB triggers last_line_partial message."""
    tool = create_bash_tool(cwd=tmp_path)
    result = await tool.execute({"command": "python -c \"print('x'*60000)\""})
    assert result.details is not None
    trunc = result.details["truncation"]
    assert trunc["truncated"] is True
    assert trunc["last_line_partial"] is True
    assert "Showing last" in _text(result)
    assert "Full output:" in _text(result)


@pytest.mark.anyio
async def test_bash_tool_truncation_byte_limit(tmp_path: Path) -> None:
    """Multiple small lines totalling > 50KB triggers byte-limit message."""
    tool = create_bash_tool(cwd=tmp_path)
    result = await tool.execute({"command": "python -c \"for i in range(1800): print('x'*30)\""})
    assert result.details is not None
    trunc = result.details["truncation"]
    assert trunc["truncated"] is True
    assert trunc["last_line_partial"] is False
    assert "limit)" in _text(result)
    assert "Full output:" in _text(result)
