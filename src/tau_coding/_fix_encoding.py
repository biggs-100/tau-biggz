"""Reconfigure std streams to UTF-8 to prevent UnicodeEncodeError on Windows.

When Tau runs in print mode (``tau -p``) on Windows, the console's default
codepage (e.g. cp1252) can cause a ``UnicodeEncodeError`` if the model
emits non-ASCII characters.  This module forces UTF-8 on ``sys.stdout``
and ``sys.stderr`` early in the CLI startup, tolerating streams that
do not support ``.reconfigure()`` (e.g. pipes, files).

Call ``reconfigure_std_streams()`` as early as possible in the CLI entry
point.
"""

from __future__ import annotations

import contextlib
import sys


def reconfigure_std_streams() -> None:
    """Force UTF-8 encoding on stdout and stderr with error replacement."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
