"""Terminal window/tab title control via OSC escape sequences.

Writes OSC 0 (``\x1b]0;<title>\x07``) to set the terminal emulator's
icon name and window title — what appears in the tab or window title bar.
"""

from __future__ import annotations

import os
import re
import sys

_MAX_TITLE_LENGTH = 80
_RE_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def set_terminal_title(title: str) -> None:
    """Write OSC 0 escape sequence to set the terminal tab/window title.

    The call is silently skipped when ``sys.stdout`` is not a terminal
    (e.g. pipes, files, CI) to avoid writing raw escape bytes to output.
    """
    if not sys.stdout.isatty():
        return
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    sanitized = _sanitize_title(title)
    try:
        sys.stdout.write(f"\x1b]0;{sanitized}\x07")
        sys.stdout.flush()
    except (UnicodeEncodeError, OSError):
        # Gracefully handle platforms where the terminal encoding cannot
        # represent the title characters (e.g. Windows cp1252 with Unicode
        # title text), or where stdout is unavailable.
        pass


def _sanitize_title(title: str) -> str:
    """Strip control characters and enforce a maximum length."""
    cleaned = _RE_CONTROL.sub("", title.strip())
    if not cleaned:
        return "Tau"
    return cleaned[:_MAX_TITLE_LENGTH]
