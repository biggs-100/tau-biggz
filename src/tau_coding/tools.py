"""Built-in filesystem and shell tools for Tau coding sessions.

The module exposes factory functions that create provider-neutral ``AgentTool``
objects plus richer ``ToolDefinition`` objects for callers that need prompt
metadata and JSON schemas. The tools operate relative to a configurable working
directory, return structured ``AgentToolResult`` values, and keep local
filesystem/shell behavior outside the reusable ``tau_agent`` package.

Private helper functions have been refactored into focused sibling modules:
``tools_types``, ``tools_validation``, ``tools_truncation``, ``tools_security``,
``tools_events``, ``tools_bash``, ``tools_edit``, and ``tools_file_lock``.
This module re-exports everything needed by existing callers.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path
from time import monotonic
from typing import Any

from tau_agent.tools import AgentTool, AgentToolResult, ToolCancellationToken
from tau_agent.types import JSONValue

from tau_coding.extensions import ToolRegistration, get_default_registry
from tau_coding.harness import HarnessApproval, SandboxConfig
from tau_coding.mcp_integration import get_mcp_registry, mcp_tool_to_agent_tool

# ── imports from refactored modules ──────────────────────────────────────
from tau_coding.tools_types import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_MAX_OUTPUT_LINES,
    SUPPORTED_IMAGE_MIME_TYPES,
    UTF8_BOM,
    ToolDefinition,
    ToolInputError,
    TruncationResult,
    _file_locks,
)
from tau_coding.tools_validation import (
    _optional_float_arg,
    _optional_int_arg,
    _path_arg,
    _str_arg,
    _validate_path_in_sandbox,
)
from tau_coding.tools_truncation import (
    append_status_block,
    format_size,
    truncate_head,
    truncate_tail,
)
from tau_coding.tools_security import _check_tool_approval, _check_trust_store
from tau_coding.tools_events import _extension_tool_to_agent_tool, _wrap_tool_with_events
from tau_coding.tools_bash import (
    _communicate_with_cancellation,
    _kill_process_tree,
    _prefixed_shell_command,
    _wait_for_cancel,
    _write_temp_output,
)
from tau_coding.tools_edit import (
    _base64_text,
    _count_occurrences,
    _detect_supported_image_mime_type,
    _duplicate_error,
    _edits_arg,
    _empty_old_text_error,
    _no_change_error,
    _not_found_error,
    _prepare_edit_arguments,
    _strip_bom,
    _validate_non_overlapping,
    apply_edits_to_normalized_content,
    detect_line_ending,
    generate_diff_string,
    generate_unified_patch,
    normalize_to_lf,
    restore_line_endings,
)
from tau_coding.tools_file_lock import _file_lock, _FileLockContext


# ── create_coding_tools ──────────────────────────────────────────────────


def create_coding_tools(
    *,
    cwd: str | Path | None = None,
    shell_command_prefix: str | None = None,
    extension_tools: list[ToolRegistration] | None = None,
    approval: HarnessApproval | None = None,
    sandbox_config: SandboxConfig | None = None,
) -> list[AgentTool]:
    """Create the default coding-tool set for a local project.

    The returned tools are ordered as ``read``, ``write``, ``edit``, and ``bash``,
    followed by any extension-registered tools.
    """
    root = Path.cwd() if cwd is None else Path(cwd)
    tools = [
        create_read_tool(cwd=root, sandbox_config=sandbox_config),
        create_write_tool(cwd=root, sandbox_config=sandbox_config),
        create_edit_tool(cwd=root, sandbox_config=sandbox_config),
        create_bash_tool(cwd=root, shell_command_prefix=shell_command_prefix),
    ]
    tools.append(create_web_search_tool())
    tools.append(create_subagent_tool())
    if extension_tools:
        for ext_tool in extension_tools:
            tools.append(_extension_tool_to_agent_tool(ext_tool))
    return [_wrap_tool_with_events(t, approval=approval) for t in tools]


# ── create_read_tool_definition / create_read_tool ───────────────────────


def create_read_tool_definition(
    *,
    cwd: str | Path | None = None,
    sandbox_config: SandboxConfig | None = None,
) -> ToolDefinition:
    """Create a definition for the ``read`` tool.

    The tool reads a file resolved relative to ``cwd`` unless an absolute path is
    supplied. Text files are decoded as UTF-8 and may be sliced with optional
    1-indexed ``offset`` and positive integer ``limit`` arguments. Returned text is
    truncated to ``DEFAULT_MAX_OUTPUT_LINES`` lines or ``DEFAULT_MAX_OUTPUT_BYTES``
    bytes, whichever comes first, and continuation hints are appended when more
    lines remain. Supported image paths (``jpg``, ``png``, ``gif``, and ``webp``) are
    detected by MIME type and returned as base64 metadata instead of text.

    The executor raises ``ToolInputError`` for invalid arguments, missing files,
    directories, and offsets beyond the end of the file. Successful results
    include the resolved path and truncation metadata in ``data``.
    """
    root = Path.cwd() if cwd is None else Path(cwd)

    async def execute(
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        del signal
        raw_path = _str_arg(arguments, "path")
        path = _path_arg(arguments, "path", cwd=root)
        _validate_path_in_sandbox(path, sandbox_config, root)
        offset = _optional_int_arg(arguments, "offset")
        limit = _optional_int_arg(arguments, "limit")

        if offset is not None and offset < 0:
            raise ToolInputError("offset must be at least 0")
        if limit is not None and limit < 1:
            raise ToolInputError("limit must be at least 1")
        if not path.exists():
            raise ToolInputError(f"File not found: {path}")
        if path.is_dir():
            raise ToolInputError(f"Path is a directory: {path}")

        mime_type = _detect_supported_image_mime_type(path)
        if mime_type is not None:
            data = path.read_bytes()
            return AgentToolResult(
                tool_call_id="",
                name="read",
                ok=True,
                content=f"Read image file [{mime_type}]",
                data={
                    "path": str(path),
                    "mime_type": mime_type,
                    "bytes": len(data),
                    "image_base64": _base64_text(data),
                },
            )

        text = path.read_text(encoding="utf-8")
        all_lines = text.split("\n")
        start_line = 0 if offset is None or offset == 0 else offset - 1

        if start_line >= len(all_lines):
            raise ToolInputError(
                f"Offset {offset} is beyond end of file ({len(all_lines)} lines total)"
            )

        user_limited_lines: int | None = None
        if limit is not None:
            end_line = min(start_line + limit, len(all_lines))
            selected = "\n".join(all_lines[start_line:end_line])
            user_limited_lines = end_line - start_line
        else:
            selected = "\n".join(all_lines[start_line:])

        truncation = truncate_head(selected)
        start_display = start_line + 1
        details: dict[str, JSONValue] = {"path": str(path), "truncation": truncation.to_json()}

        if truncation.first_line_exceeds_limit:
            first_line_size = format_size(len(all_lines[start_line].encode()))
            output = (
                f"[Line {start_display} is {first_line_size}, exceeds "
                f"{format_size(DEFAULT_MAX_OUTPUT_BYTES)} limit. Use bash: sed -n "
                f"'{start_display}p' {raw_path} | head -c {DEFAULT_MAX_OUTPUT_BYTES}]"
            )
        elif truncation.truncated:
            end_display = start_display + truncation.output_lines - 1
            next_offset = end_display + 1
            output = truncation.content
            if truncation.truncated_by == "lines":
                output += (
                    f"\n\n[Showing lines {start_display}-{end_display} of {len(all_lines)}. "
                    f"Use offset={next_offset} to continue.]"
                )
            else:
                output += (
                    f"\n\n[Showing lines {start_display}-{end_display} of {len(all_lines)} "
                    f"({format_size(DEFAULT_MAX_OUTPUT_BYTES)} limit). "
                    f"Use offset={next_offset} to continue.]"
                )
        elif user_limited_lines is not None and start_line + user_limited_lines < len(all_lines):
            remaining = len(all_lines) - (start_line + user_limited_lines)
            next_offset = start_line + user_limited_lines + 1
            output = (
                f"{truncation.content}\n\n[{remaining} more lines in file. "
                f"Use offset={next_offset} to continue.]"
            )
        else:
            output = truncation.content

        return AgentToolResult(
            tool_call_id="",
            name="read",
            ok=True,
            content=output,
            data=details,
        )

    return ToolDefinition(
        name="read",
        description=(
            "Read the contents of a file. Supports text files and images (jpg, png, gif, webp). "
            "Images are returned as base64 metadata. For text files, output is truncated to "
            f"{DEFAULT_MAX_OUTPUT_LINES} lines or {DEFAULT_MAX_OUTPUT_BYTES // 1024}KB "
            "(whichever is hit first). Use offset/limit for large files. When you need the "
            "full file, continue with offset until complete."
        ),
        prompt_snippet="Read file contents",
        prompt_guidelines=("Use read to examine files instead of cat or sed.",),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read"},
                "offset": {"type": "integer", "description": "Line number to start reading from"},
                "limit": {"type": "integer", "description": "Maximum number of lines to read"},
            },
            "required": ["path"],
        },
        executor=execute,
    )


def create_read_tool(
    *,
    cwd: str | Path | None = None,
    sandbox_config: SandboxConfig | None = None,
) -> AgentTool:
    """Create an ``AgentTool`` for reading UTF-8 text files and supported images."""
    return create_read_tool_definition(cwd=cwd, sandbox_config=sandbox_config).to_agent_tool()


# ── create_write_tool_definition / create_write_tool ─────────────────────


def create_write_tool_definition(
    *,
    cwd: str | Path | None = None,
    sandbox_config: SandboxConfig | None = None,
) -> ToolDefinition:
    """Create a definition for the ``write`` tool.

    The tool writes the supplied string ``content`` to ``path``, resolving relative
    paths against ``cwd``. Parent directories are created automatically and any
    existing file is overwritten. Writes use UTF-8 text encoding and are guarded
    by a per-path async lock so multiple writes/edits to the same resolved file
    are serialized within this process.

    The executor raises ``ToolInputError`` when ``path`` or ``content`` has the wrong
    type. Successful results include the resolved path and number of characters
    written in ``data``.
    """
    root = Path.cwd() if cwd is None else Path(cwd)

    async def execute(
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        del signal
        path = _path_arg(arguments, "path", cwd=root)
        _validate_path_in_sandbox(path, sandbox_config, root)
        content = _str_arg(arguments, "content")

        async with _file_lock(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        return AgentToolResult(
            tool_call_id="",
            name="write",
            ok=True,
            content=f"Successfully wrote to {path}.",
            data={"path": str(path), "characters": len(content)},
        )

    return ToolDefinition(
        name="write",
        description=(
            "Write content to a file. Creates the file if it doesn't exist, overwrites if it does. "
            "Automatically creates parent directories."
        ),
        prompt_snippet="Create or overwrite files",
        prompt_guidelines=("Use write only for new files or complete rewrites.",),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to write"},
                "content": {"type": "string", "description": "Content to write to the file"},
            },
            "required": ["path", "content"],
        },
        executor=execute,
    )


def create_write_tool(
    *,
    cwd: str | Path | None = None,
    sandbox_config: SandboxConfig | None = None,
) -> AgentTool:
    """Create an ``AgentTool`` for creating or overwriting UTF-8 text files."""
    return create_write_tool_definition(cwd=cwd, sandbox_config=sandbox_config).to_agent_tool()


# ── create_edit_tool_definition / create_edit_tool ───────────────────────


def create_edit_tool_definition(
    *,
    cwd: str | Path | None = None,
    sandbox_config: SandboxConfig | None = None,
) -> ToolDefinition:
    """Create a definition for the ``edit`` tool.

    The tool applies one or more exact text replacements to a single UTF-8 file
    resolved relative to ``cwd``. Each edit item contains ``oldText`` and ``newText``.
    Every ``oldText`` must be non-empty, must occur exactly once in the original
    file, and must not overlap another edit span. All replacements are validated
    before writing, so the file is left unchanged if any edit fails.

    File content and edit text are normalized to LF for matching, then the
    original file's dominant line ending is restored after replacement. UTF-8
    byte-order marks are preserved. The executor also accepts legacy top-level
    ``oldText``/``newText`` arguments and JSON-string ``edits`` values by normalizing
    them into the canonical edits list.

    Successful results include the resolved path, edit count, an ndiff-style
    diff, a unified patch, and the first changed line in ``data``.
    """
    root = Path.cwd() if cwd is None else Path(cwd)

    async def execute(
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        del signal
        prepared = _prepare_edit_arguments(arguments)
        path = _path_arg(prepared, "path", cwd=root)
        _validate_path_in_sandbox(path, sandbox_config, root)
        edits = _edits_arg(prepared)

        if not path.exists():
            raise ToolInputError(f"Could not edit file: {path}. File not found.")
        if path.is_dir():
            raise ToolInputError(f"Could not edit file: {path}. Path is a directory.")

        async with _file_lock(path):
            raw_content = path.read_text(encoding="utf-8")
            bom, content = _strip_bom(raw_content)
            original_ending = detect_line_ending(content)
            normalized = normalize_to_lf(content)
            base_content, new_content = apply_edits_to_normalized_content(
                normalized, edits, str(path)
            )
            final_content = bom + restore_line_endings(new_content, original_ending)
            path.write_text(final_content, encoding="utf-8")

        diff_text, first_changed_line = generate_diff_string(base_content, new_content)
        patch = generate_unified_patch(str(path), base_content, new_content)
        return AgentToolResult(
            tool_call_id="",
            name="edit",
            ok=True,
            content=f"Successfully replaced {len(edits)} block(s) in {path}.",
            data={
                "path": str(path),
                "edits": len(edits),
                "diff": diff_text,
                "patch": patch,
                "first_changed_line": first_changed_line,
            },
        )

    return ToolDefinition(
        name="edit",
        description=(
            "Edit a single file using exact text replacement. Every edits[].oldText must match "
            "a unique, non-overlapping region of the original file. If two changes affect the "
            "same block or nearby lines, merge them into one edit instead of emitting overlapping "
            "edits. Do not include large unchanged regions just to connect distant changes."
        ),
        prompt_snippet=(
            "Make precise file edits with exact text replacement, including multiple disjoint "
            "edits in one call"
        ),
        prompt_guidelines=(
            "Use edit for precise changes (edits[].oldText must match exactly)",
            "When changing multiple separate locations in one file, use one edit call with "
            "multiple entries in edits[] instead of multiple edit calls",
            "Each edits[].oldText is matched against the original file, not after earlier "
            "edits are applied. Do not emit overlapping or nested edits. Merge nearby "
            "changes into one edit.",
            "Keep edits[].oldText as small as possible while still being unique in the file. "
            "Do not pad with large unchanged regions.",
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to edit"},
                "edits": {
                    "type": "array",
                    "description": "One or more targeted replacements.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "oldText": {"type": "string"},
                            "newText": {"type": "string"},
                        },
                        "required": ["oldText", "newText"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["path", "edits"],
            "additionalProperties": False,
        },
        executor=execute,
    )


def create_edit_tool(
    *,
    cwd: str | Path | None = None,
    sandbox_config: SandboxConfig | None = None,
) -> AgentTool:
    """Create an ``AgentTool`` for exact, validated text replacement in one file."""
    return create_edit_tool_definition(cwd=cwd, sandbox_config=sandbox_config).to_agent_tool()


# ── create_bash_tool_definition / create_bash_tool ───────────────────────


def create_bash_tool_definition(
    *,
    cwd: str | Path | None = None,
    shell_command_prefix: str | None = None,
) -> ToolDefinition:
    """Create a definition for the ``bash`` tool.

    The tool runs a shell command with ``cwd`` as the subprocess working
    directory and combines stdout and stderr into one UTF-8 decoded output
    stream. The optional ``timeout`` argument must be positive when supplied. On
    timeout, POSIX commands are started in a new session and the entire process
    group is killed so shell children from pipelines or compound commands do
    not continue running; non-POSIX platforms fall back to killing the direct
    subprocess.

    Output is tail-truncated to ``DEFAULT_MAX_OUTPUT_LINES`` lines or
    ``DEFAULT_MAX_OUTPUT_BYTES`` bytes. When truncation occurs, the full output is
    written to a temporary log file and that path is reported in ``data``.
    Successful and failed command results both include exit code, timeout state,
    duration, truncation metadata, and full-output path metadata.
    """
    root = Path.cwd() if cwd is None else Path(cwd)
    prefix = shell_command_prefix.strip() if shell_command_prefix else None

    async def execute(
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        command = _str_arg(arguments, "command")
        shell_command = _prefixed_shell_command(command, prefix)
        timeout = _optional_float_arg(arguments, "timeout")
        if timeout is not None and timeout <= 0:
            raise ToolInputError("timeout must be greater than 0")
        if signal is not None and signal.is_cancelled():
            raise ToolInputError("Command cancelled")

        start = monotonic()
        if os.name == "posix":
            process = await asyncio.create_subprocess_shell(
                shell_command,
                cwd=root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
                executable="bash" if prefix else None,
            )
        else:
            process = await asyncio.create_subprocess_shell(
                shell_command,
                cwd=root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        output_bytes, _stderr, timed_out, cancelled = await _communicate_with_cancellation(
            process,
            timeout=timeout,
            signal=signal,
        )

        output = output_bytes.decode(errors="replace")
        truncation = truncate_tail(output)
        full_output_path: str | None = None
        output_text = truncation.content or "(no output)"
        if truncation.truncated:
            full_output_path = _write_temp_output(output)
            start_line = truncation.total_lines - truncation.output_lines + 1
            end_line = truncation.total_lines
            if truncation.last_line_partial:
                output_text += (
                    f"\n\n[Showing last {format_size(truncation.output_bytes)} of line {end_line}. "
                    f"Full output: {full_output_path}]"
                )
            elif truncation.truncated_by == "lines":
                output_text += (
                    f"\n\n[Showing lines {start_line}-{end_line} of {truncation.total_lines}. "
                    f"Full output: {full_output_path}]"
                )
            else:
                output_text += (
                    f"\n\n[Showing lines {start_line}-{end_line} of {truncation.total_lines} "
                    f"({format_size(DEFAULT_MAX_OUTPUT_BYTES)} limit). "
                    f"Full output: {full_output_path}]"
                )

        exit_code = process.returncode
        status: str | None = None
        if timed_out:
            status = (
                f"Command timed out after {timeout:g} seconds" if timeout else "Command timed out"
            )
        elif cancelled:
            status = "Command cancelled"
        elif exit_code not in (0, None):
            status = f"Command exited with code {exit_code}"
        if status:
            output_text = append_status_block(output_text, status)

        ok = exit_code == 0 and not timed_out and not cancelled
        return AgentToolResult(
            tool_call_id="",
            name="bash",
            ok=ok,
            content=output_text,
            error=None if ok else status,
            data={
                "command": command,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "cancelled": cancelled,
                "duration_seconds": round(monotonic() - start, 3),
                "truncation": truncation.to_json(),
                "full_output_path": full_output_path,
                "shell_command_prefix_applied": prefix is not None,
            },
        )

    return ToolDefinition(
        name="bash",
        description=(
            "Execute a bash command in the current working directory. Returns stdout and stderr. "
            f"Output is truncated to last {DEFAULT_MAX_OUTPUT_LINES} lines or "
            f"{DEFAULT_MAX_OUTPUT_BYTES // 1024}KB (whichever is hit first). If truncated, "
            "full output is saved to a temp file. Optionally provide a timeout in seconds."
        ),
        prompt_snippet="Execute bash commands (ls, grep, find, etc.)",
        prompt_guidelines=(),
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Bash command to execute"},
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (optional, no default timeout)",
                },
            },
            "required": ["command"],
        },
        executor=execute,
    )


def create_bash_tool(
    *,
    cwd: str | Path | None = None,
    shell_command_prefix: str | None = None,
) -> AgentTool:
    """Create an ``AgentTool`` for executing shell commands with captured output."""
    return create_bash_tool_definition(
        cwd=cwd,
        shell_command_prefix=shell_command_prefix,
    ).to_agent_tool()


# ── create_web_search_tool ───────────────────────────────────────────────


def create_web_search_tool() -> AgentTool:
    """Create an AgentTool for web searching via DuckDuckGo."""
    import httpx
    import re

    input_schema: dict[str, JSONValue] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query",
            },
        },
        "required": ["query"],
    }

    async def search_executor(
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        query = str(arguments.get("query", ""))
        if not query:
            return AgentToolResult(
                tool_call_id="web",
                name="web_search",
                ok=False,
                content="No search query provided.",
                error="Missing query",
            )
        try:
            url = "https://html.duckduckgo.com/html/"
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, data={"q": query})
                resp.raise_for_status()
                text = resp.text

            results = []
            for match in re.finditer(
                r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>\s*<h[^>]*>(.*?)</h',
                text,
                re.DOTALL,
            ):
                url_result = match.group(1)
                title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                results.append(f"{title}\n{url_result}")
                if len(results) >= 8:
                    break

            if not results:
                return AgentToolResult(
                    tool_call_id="web",
                    name="web_search",
                    ok=True,
                    content="No results found.",
                )

            return AgentToolResult(
                tool_call_id="web",
                name="web_search",
                ok=True,
                content="\n\n---\n\n".join(results),
            )
        except Exception as exc:
            return AgentToolResult(
                tool_call_id="web",
                name="web_search",
                ok=False,
                content=f"Search failed: {exc}",
                error=str(exc),
            )

    return AgentTool(
        name="web_search",
        description="Search the web using DuckDuckGo. Returns up to 8 results with titles and URLs.",
        input_schema=input_schema,
        executor=search_executor,
        prompt_snippet="Search the web for information.",
    )


# ── create_subagent_tool ─────────────────────────────────────────────────


def create_subagent_tool() -> AgentTool:
    """Create an AgentTool for spawning sub-agents from agent markdown files."""
    from tau_agent import AgentHarness, AgentHarnessConfig

    input_schema: dict[str, JSONValue] = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The task or question for the sub-agent",
            },
            "agent": {
                "type": "string",
                "description": "Agent name from .tau/agents/<name>.md",
            },
            "instructions": {
                "type": "string",
                "description": "Inline system prompt (overrides agent file if set)",
            },
        },
        "required": ["task"],
    }

    async def subagent_executor(
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        task = str(arguments.get("task", ""))
        agent_name = str(arguments.get("agent", "")) or None
        instructions = str(arguments.get("instructions", "")) or None
        if not task:
            return AgentToolResult(
                tool_call_id="sub", name="subagent_run", ok=False, content="No task provided."
            )

        try:
            system_prompt = None
            if agent_name:
                from tau_coding.agents import load_agent

                ad = load_agent(agent_name)
                if ad:
                    system_prompt = ad.system_prompt
            if instructions:
                system_prompt = instructions
            if not system_prompt:
                system_prompt = "You are a helpful sub-agent. Complete the assigned task concisely."

            from tau_coding.provider_config import load_provider_settings
            from tau_coding.provider_runtime import create_model_provider

            settings = load_provider_settings()
            if not settings or not settings.providers:
                return AgentToolResult(
                    tool_call_id="sub", name="subagent_run", ok=False,
                    content="No provider configured. Login with /login first.",
                )

            first = settings.providers[0]
            model = first.default_model
            provider = create_model_provider(first, model=model)

            harness = AgentHarness(
                AgentHarnessConfig(provider=provider, model=model, system=system_prompt, tools=[]),
            )
            text_parts = []
            async for event in harness.prompt(task):
                from tau_agent import AgentEndEvent, ErrorEvent

                if isinstance(event, AgentEndEvent):
                    text_parts.append(event.message.content or "")
                elif isinstance(event, ErrorEvent) and not event.recoverable:
                    await provider.aclose()
                    return AgentToolResult(
                        tool_call_id="sub", name="subagent_run", ok=False,
                        content=f"Sub-agent error: {event.message}",
                    )
            result_text = "".join(text_parts).strip()
            await provider.aclose()
            return AgentToolResult(
                tool_call_id="sub", name="subagent_run", ok=True,
                content=result_text or "(no response)",
            )
        except Exception as exc:
            return AgentToolResult(
                tool_call_id="sub", name="subagent_run", ok=False,
                content=f"Sub-agent failed: {exc}", error=str(exc),
            )

    return AgentTool(
        name="subagent_run",
        description="Spawn a sub-agent. agent=.tau/agents/<name>.md, instructions=inline prompt.",
        input_schema=input_schema,
        executor=subagent_executor,
        prompt_snippet="Delegate tasks to sub-agents for parallel or specialized work.",
    )
