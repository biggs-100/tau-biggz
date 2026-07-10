"""Miscellaneous utility functions for the coding-session subsystem."""

from __future__ import annotations

from tau_coding.session_models import TerminalCommandRequest


def _auto_session_name_from_text(text: str) -> str | None:
    """Derive a short session name (3-4 words) from the first user message."""
    import re

    cleaned = re.sub(r"[^\w\s]", " ", text).strip()
    words = [
        w
        for w in cleaned.split()
        if w.lower()
        not in {
            "a",
            "an",
            "the",
            "is",
            "are",
            "was",
            "were",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "and",
            "or",
            "but",
        }
    ]
    if not words:
        return None
    name = " ".join(words[:4])
    if not name:
        return None
    return name[0].upper() + name[1:] if len(name) > 1 else name


def _terminal_command_context_message(command: str, output: str) -> str:
    return (
        "Terminal command executed by the user.\n\n"
        f"Command:\n```bash\n{command}\n```\n\n"
        f"Output:\n```text\n{output}\n```"
    )


def parse_terminal_command(text: str) -> TerminalCommandRequest | None:
    """Parse input-bar terminal command syntax."""
    stripped = text.strip()
    if stripped.startswith("!!"):
        command = stripped[2:].strip()
        if not command:
            return None
        return TerminalCommandRequest(command=command, add_to_context=False)
    if stripped.startswith("!"):
        command = stripped[1:].strip()
        if not command:
            return None
        return TerminalCommandRequest(command=command, add_to_context=True)
    return None
