"""Example extension: status bar widget.

Install by placing this file in ~/.tau/extensions/ or .tau/extensions/.
"""

from __future__ import annotations

import datetime

from tau_coding.extensions import Extension, ui_widget


class UiStatusExt(Extension):
    """Demonstrates extension UI widgets in the status bar."""

    @ui_widget("status-bar")
    def clock(self) -> str:
        """Return the current time for the status bar."""
        return f"🕒 {datetime.datetime.now():%H:%M:%S}"

    @ui_widget("status-bar")
    def greeting(self) -> str:
        """Return a greeting."""
        return "👋 Tau ready"
