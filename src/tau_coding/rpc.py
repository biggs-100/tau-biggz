"""RPC mode for Tau — JSONL protocol over stdin/stdout.

Start with ``tau --rpc``. Accepts JSON commands on stdin, streams
agent events and responses to stdout.

Protocol:
- LF-delimited JSONL (``\\n`` only, no Unicode separators)
- Commands have ``type`` and optional ``id`` for correlation
- Responses have ``type: "response"`` with matching ``id``
- Agent events stream as ``type: "event"`` with the event payload

Supported commands: ``prompt``, ``cancel``, ``get_state``, ``set_model``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tau_agent.events import (
    AgentEndEvent,
    AgentEvent,
    AgentStartEvent,
    MessageDeltaEvent,
    MessageEndEvent,
    MessageStartEvent,
    ThinkingDeltaEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from tau_coding.provider_config import (
    load_provider_settings,
    resolve_provider_selection,
)
from tau_coding.provider_runtime import create_model_provider
from tau_coding.session import CodingSession, CodingSessionConfig
from tau_coding.session_manager import SessionManager

# ── protocol types ─────────────────────────────────────────────────────


@dataclass
class RpcCommand:
    """A parsed RPC command from stdin."""

    id: str | None = None
    type: str = ""
    data: dict[str, Any] = None  # type: ignore[assignment]


@dataclass
class RpcResponse:
    """A response sent to stdout."""

    id: str | None = None
    type: str = "response"
    command: str = ""
    success: bool = True
    error: str | None = None
    data: dict[str, Any] = None  # type: ignore[assignment]


# ── I/O helpers ─────────────────────────────────────────────────────────


def _write_json(obj: dict[str, Any]) -> None:
    """Write a JSON line to stdout."""
    line = json.dumps(obj, default=str) + "\n"
    sys.stdout.write(line)
    sys.stdout.flush()


async def _read_stdin() -> AsyncIterator[RpcCommand]:
    """Yield parsed commands from stdin (one per line)."""
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        try:
            raw = await reader.readline()
        except (ConnectionError, OSError):
            return

        if not raw:
            return  # EOF

        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue

        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            _write_json(
                {
                    "type": "response",
                    "error": f"Invalid JSON: {exc}",
                    "success": False,
                }
            )
            continue

        yield RpcCommand(
            id=obj.get("id"),
            type=obj.get("type", ""),
            data=obj,
        )


# ── event streaming ─────────────────────────────────────────────────────


def _event_to_dict(event: AgentEvent) -> dict[str, Any]:
    """Convert an AgentEvent to a JSON-serializable dict."""
    name = type(event).__name__.removesuffix("Event").lower()

    payload: dict[str, Any] = {"type": "event", "event": name}

    if isinstance(event, AgentStartEvent):
        payload["session_id"] = event.session_id  # type: ignore[attr-defined]
    elif isinstance(event, MessageStartEvent):
        payload["role"] = event.message.role if event.message else "assistant"
    elif isinstance(event, MessageDeltaEvent):
        payload["delta"] = event.delta
    elif isinstance(event, MessageEndEvent):
        payload["role"] = event.message.role if event.message else None
        if event.message is not None:
            from tau_agent.messages import TextContent
            content_text = "".join(b.text for b in event.message.content if isinstance(b, TextContent))
            payload["content"] = content_text[:500]
    elif isinstance(event, ToolExecutionStartEvent):
        payload["tool_name"] = event.tool_name  # type: ignore[attr-defined]
        payload["tool_input"] = str(event.args)[:200] if event.args else None  # type: ignore[attr-defined]
    elif isinstance(event, ToolExecutionEndEvent):
        payload["tool_name"] = event.tool_name  # type: ignore[attr-defined]
        payload["ok"] = not event.is_error  # type: ignore[attr-defined]
        result_str = ""
        if event.result is not None and hasattr(event.result, "content"):
            from tau_agent.messages import TextContent
            result_str = "".join(b.text for b in event.result.content if isinstance(b, TextContent))
        payload["result"] = result_str[:200] if result_str else None
    elif isinstance(event, ThinkingDeltaEvent):
        payload["delta"] = event.delta[:200] if event.delta else None
    elif isinstance(event, AgentEndEvent):
        payload["ok"] = True

    return {k: v for k, v in payload.items() if v is not None}


# ── session run ─────────────────────────────────────────────────────────


async def _run_prompt(session: CodingSession, prompt: str) -> None:
    """Run a prompt and stream events to stdout."""
    try:
        async for event in session.prompt(prompt):
            _write_json(_event_to_dict(event))
    except Exception as exc:
        _write_json(
            {
                "type": "event",
                "event": "error",
                "error": str(exc),
            }
        )


# ── main RPC loop ───────────────────────────────────────────────────────


async def run_rpc_mode(*, cwd: Path | None = None) -> None:
    """Run Tau in RPC mode, processing commands from stdin."""
    resolved_cwd = cwd or Path.cwd()
    provider_settings = load_provider_settings()
    manager = SessionManager()
    session: CodingSession | None = None
    current_task: asyncio.Task[None] | None = None

    _write_json(
        {
            "type": "event",
            "event": "ready",
            "cwd": str(resolved_cwd),
        }
    )

    async for cmd in _read_stdin():
        # ── cancel ──────────────────────────────────────────────────────
        if cmd.type == "cancel":
            if current_task is not None and not current_task.done():
                current_task.cancel()
                current_task = None

            # Cancel the session's current run
            if session is not None:
                with contextlib.suppress(Exception):
                    session.cancel()

            _write_json(RpcResponse(id=cmd.id, command="cancel", success=True).__dict__)
            continue

        # ── get_state ────────────────────────────────────────────────────
        if cmd.type == "get_state":
            if session is None:
                _write_json(
                    RpcResponse(
                        id=cmd.id, command="get_state", success=False, error="No active session"
                    ).__dict__
                )
                continue

            state = {
                "model": session.model,
                "provider": session.provider_name,
                "thinking_level": session.thinking_level,
                "running": session.is_running,
                "session_id": session.session_id,
            }
            _write_json(
                RpcResponse(id=cmd.id, command="get_state", success=True, data=state).__dict__
            )
            continue

        # ── set_model ───────────────────────────────────────────────────
        if cmd.type == "set_model":
            provider_name = cmd.data.get("provider") or "openai"
            model = cmd.data.get("model", "")

            try:
                if session is None:
                    # Create session with new provider/model
                    selection = resolve_provider_selection(
                        provider_settings,
                        provider_name=provider_name,
                        model=model or None,
                    )
                    provider = create_model_provider(
                        selection.provider,
                        model=selection.model,
                    )
                    record = manager.prepare_session(
                        cwd=resolved_cwd,
                        model=selection.model,
                        provider_name=selection.provider.name,
                    )
                    session = await CodingSession.load(
                        CodingSessionConfig(
                            provider=provider,
                            model=record.model,
                            cwd=record.cwd,
                            storage=type("S", (), {"path": record.path})(),
                            session_id=record.id,
                            session_manager=manager,
                            provider_name=selection.provider.name,
                            provider_settings=provider_settings,
                            runtime_provider_config=selection.provider,
                        )
                    )
                else:
                    session.set_model(model)

                _write_json(RpcResponse(id=cmd.id, command="set_model", success=True).__dict__)
            except Exception as exc:
                _write_json(
                    RpcResponse(
                        id=cmd.id, command="set_model", success=False, error=str(exc)
                    ).__dict__
                )
            continue

        # ── prompt ──────────────────────────────────────────────────────
        if cmd.type == "prompt":
            message = cmd.data.get("message", "")
            if not message:
                _write_json(
                    RpcResponse(
                        id=cmd.id, command="prompt", success=False, error="Empty message"
                    ).__dict__
                )
                continue

            try:
                # Ensure session exists
                if session is None:
                    selection = resolve_provider_selection(provider_settings)
                    provider = create_model_provider(
                        selection.provider,
                        model=selection.model,
                    )
                    record = manager.prepare_session(
                        cwd=resolved_cwd,
                        model=selection.model,
                        provider_name=selection.provider.name,
                    )
                    session = await CodingSession.load(
                        CodingSessionConfig(
                            provider=provider,
                            model=record.model,
                            cwd=record.cwd,
                            storage=type("S", (), {"path": record.path})(),
                            session_id=record.id,
                            session_manager=manager,
                            provider_name=selection.provider.name,
                            provider_settings=provider_settings,
                            runtime_provider_config=selection.provider,
                        )
                    )

                # Accept the prompt
                _write_json(RpcResponse(id=cmd.id, command="prompt", success=True).__dict__)

                # Run prompt and stream events (in background if already running)
                if session.is_running:
                    session.steer(message)
                else:
                    if current_task is not None and not current_task.done():
                        current_task.cancel()
                    current_task = asyncio.create_task(_run_prompt(session, message))

            except Exception as exc:
                _write_json(
                    RpcResponse(id=cmd.id, command="prompt", success=False, error=str(exc)).__dict__
                )
            continue

        # ── unknown command ─────────────────────────────────────────────
        _write_json(
            RpcResponse(
                id=cmd.id, command=cmd.type, success=False, error=f"Unknown command: {cmd.type}"
            ).__dict__
        )

    # Wait for any running task on EOF
    if current_task is not None and not current_task.done():
        with contextlib.suppress(asyncio.CancelledError):
            await current_task
