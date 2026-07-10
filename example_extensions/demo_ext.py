"""Demo Extension — comprehensive example of all Tau extension features.

This extension demonstrates every feature the Tau extension system offers:

- ``@tool`` decorator for custom AI tools (``demo_greet``)
- ``@command`` decorator for slash commands (``/demo``)
- ``@on`` decorator for event handlers (``session_start``, ``session_end``, ``tool_call``)
- ``@ui_widget`` decorator for status bar widgets (tool call counter)
- ``on_load()`` / ``on_unload()`` lifecycle hooks

Copy this file to ``~/.tau/extensions/`` or use the extension install command::

    from tau_coding.extensions import get_default_registry
    reg = get_default_registry()
    reg.install_extension("path/to/demo_ext.py")
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tau_coding.extensions import Extension, command, on, tool, ui_widget


class DemoExtension(Extension):
    """Comprehensive demo of all Tau extension features.

    Features demonstrated:
    - **Tool registration**: ``@tool("demo_greet")`` — used by the AI model.
    - **Slash commands**: ``@command("demo")`` — interactive user commands.
    - **Event handlers**: ``@on("session_start")``, ``@on("session_end")``,
      ``@on("tool_call")`` — react to framework events.
    - **UI widgets**: ``@ui_widget(zone="status-bar")`` — live status display.
    - **Lifecycle hooks**: ``on_load()`` and ``on_unload()`` — setup/teardown.
    """

    def __init__(self) -> None:
        self._tool_call_count: int = 0
        self._log_dir: Path | None = None

    # ── Lifecycle hooks ───────────────────────────────────────────────────

    def on_load(self) -> None:
        """Set up extension resources when loaded.

        Creates a log directory in the system temp folder and writes
        a JSON entry recording the load event.
        """
        self._log_dir = Path(tempfile.gettempdir()) / "tau_demo_ext"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._write_log("on_load", {"status": "extension loaded"})

    def on_unload(self) -> None:
        """Clean up when the extension is unloaded.

        Writes a final log entry before the extension is removed from
        the registry.
        """
        self._write_log("on_unload", {"status": "extension unloaded"})

    # ── Tools (used by AI model) ──────────────────────────────────────────

    @tool("demo_greet", "Greet someone by name")
    def greet(self, name: str = "world") -> str:
        """Return a friendly greeting.

        The AI model can call this tool to greet the user. Tool definitions
        are automatically exposed to the model via ``get_default_registry()``.

        Args:
            name: The name to greet (default: ``"world"``).

        Returns:
            A greeting string like ``"Hello, Alex! 👋"``.
        """
        return f"Hello, {name}! 👋"

    # ── Commands (slash commands for the user) ────────────────────────────

    @command("demo", description="Show extension status information")
    def demo_cmd(self, args: str) -> str:
        """Slash command that displays demo extension status.

        Usage::

            /demo           — show basic status (tool call count, log dir)
            /demo verbose   — show detailed status including registered events

        Args:
            args: Command arguments (``"verbose"`` for extra detail).
        """
        verbose = "verbose" in args.lower()
        lines = [
            "╔══════════════════════════════════╗",
            "║  DemoExtension Status            ║",
            "╚══════════════════════════════════╝",
            f"  Tool calls tracked: {self._tool_call_count}",
            f"  Log directory: {self._log_dir}",
        ]
        if verbose:
            events = ["session_start", "session_end", "tool_call"]
            lines.append(f"  Registered events: {', '.join(events)}")
            if self._log_dir and self._log_dir.exists():
                log_files = list(self._log_dir.glob("*.log"))
                lines.append(f"  Log files: {log_files}")
        return "\n".join(lines)

    # ── Event handlers ────────────────────────────────────────────────────

    @on("session_start")
    def on_session_start(self, event: dict) -> None:
        """Log session start events.

        Triggered when a new Tau coding session begins. The event dict
        typically contains a ``session_id`` key.
        """
        self._write_log("session_start", {
            "session_id": event.get("session_id", "unknown"),
        })

    @on("session_end")
    def on_session_end(self, event: dict) -> None:
        """Log session end events.

        Triggered when a session ends. The event dict may contain
        ``session_id`` and ``duration`` keys.
        """
        self._write_log("session_end", {
            "session_id": event.get("session_id", "unknown"),
            "duration": event.get("duration", "unknown"),
        })

    @on("tool_call")
    def on_tool_call(self, event: dict) -> dict | None:
        """Monitor tool usage and block dangerous commands.

        This handler is called before every tool invocation. It:
        1. Increments the internal tool call counter (displayed in the
           status bar via ``@ui_widget``).
        2. Blocks ``bash`` tool calls that contain ``rm -rf`` in the
           command string.

        Event structure (relevant fields)::

            {
                "tool_name": "bash",
                "input": {"command": "rm -rf /"},
                "tool_call_id": "..."
            }

        Returns:
            ``{"block": True, "reason": "..."}`` to block the tool,
            or ``None`` to allow it.
        """
        self._tool_call_count += 1
        tool_name = event.get("tool_name", "")
        if tool_name == "bash":
            cmd = event.get("input", {}).get("command", "")
            if "rm -rf" in cmd:
                return {
                    "block": True,
                    "reason": "Blocked by DemoExtension safety check: "
                              "rm -rf is not allowed",
                }
        return None

    # ── UI Widgets ────────────────────────────────────────────────────────

    @ui_widget(zone="status-bar")
    def tool_counter(self) -> str:
        """Show a live tool call counter in the status bar.

        The ``@ui_widget`` decorator registers this method as a widget
        that is called periodically by the UI to refresh its display.
        The ``zone`` parameter determines where the widget appears
        (e.g. ``"status-bar"``, ``"sidebar"``).
        """
        return f"🔧 {self._tool_call_count}"

    # ── Internal helpers ──────────────────────────────────────────────────

    def _write_log(self, event: str, data: dict) -> None:
        """Append a JSON log entry to the extension log file.

        Each entry is a single JSON object written on one line
        (JSON Lines format — ``.jsonl``).

        Args:
            event: The event name (e.g. ``"session_start"``).
            data: Key-value data to include in the log entry.
        """
        if self._log_dir is None:
            return
        log_file = self._log_dir / "events.jsonl"
        entry = {"event": event, "data": data}
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass  # Silently ignore write errors in demo code
