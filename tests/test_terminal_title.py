"""Tests for tau_coding.tui._terminal_title.

Covers ``_sanitize_title`` (control chars, length, unicode, empty) and
``set_terminal_title`` (tty vs non-tty, env guard, exception handling).
"""

from __future__ import annotations

import sys

import pytest

from tau_coding.tui._terminal_title import _sanitize_title, set_terminal_title

# ── _sanitize_title ───────────────────────────────────────────────────────────


class TestSanitizeTitle:
    def test_normal_string(self) -> None:
        assert _sanitize_title("Hello World") == "Hello World"

    def test_strips_control_characters(self) -> None:
        assert _sanitize_title("Hello\x00World\x1b[Test\x7f") == "HelloWorld[Test"

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert _sanitize_title("   Tau   ") == "Tau"

    def test_empty_string_falls_back_to_tau(self) -> None:
        assert _sanitize_title("") == "Tau"

    def test_only_control_chars_falls_back_to_tau(self) -> None:
        assert _sanitize_title("\x00\x1b\x7f") == "Tau"

    def test_truncates_at_max_length(self) -> None:
        long_title = "a" * 100
        result = _sanitize_title(long_title)
        assert len(result) == 80
        assert result == "a" * 80

    def test_preserves_unicode(self) -> None:
        assert _sanitize_title("τ = 2π") == "τ = 2π"

    def test_unicode_within_max_length(self) -> None:
        long_unicode = "✓" * 100
        result = _sanitize_title(long_unicode)
        assert len(result) == 80
        assert result == "✓" * 80

    def test_control_chars_within_unicode(self) -> None:
        assert _sanitize_title("\x00τ\x00=\x002π\x00") == "τ=2π"

    def test_newline_tab_are_stripped(self) -> None:
        assert _sanitize_title("line1\nline2\tend") == "line1line2end"


# ── set_terminal_title ────────────────────────────────────────────────────────


class TestSetTerminalTitle:
    """Uses ``monkeypatch.setattr`` on ``sys.stdout`` and
    ``monkeypatch.delenv`` on ``PYTEST_CURRENT_TEST`` to isolate tests."""

    def test_writes_osc_escape_when_tty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        written: list[str] = []
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "write", written.append)
        monkeypatch.setattr(sys.stdout, "flush", lambda: None)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        set_terminal_title("Hello")

        assert written == ["\x1b]0;Hello\x07"]

    def test_writes_sanitized_title(self, monkeypatch: pytest.MonkeyPatch) -> None:
        written: list[str] = []
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "write", written.append)
        monkeypatch.setattr(sys.stdout, "flush", lambda: None)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        set_terminal_title("Hello\x00World\x1b[Test\x7f")

        assert written == ["\x1b]0;HelloWorld[Test\x07"]

    def test_truncates_long_title_in_escape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        written: list[str] = []
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "write", written.append)
        monkeypatch.setattr(sys.stdout, "flush", lambda: None)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        set_terminal_title("a" * 200)

        assert written == [f"\x1b]0;{'a' * 80}\x07"]

    def test_handles_unicode_encode_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise_unicode_error(s: str) -> None:
            raise UnicodeEncodeError("utf-8", s, 0, 1, "can't encode")

        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "write", _raise_unicode_error)
        monkeypatch.setattr(sys.stdout, "flush", lambda: None)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        # Must not raise
        set_terminal_title("Hello")

    def test_handles_os_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise_os_error(s: str) -> None:
            raise OSError("broken stdout")

        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "write", _raise_os_error)
        monkeypatch.setattr(sys.stdout, "flush", lambda: None)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        # Must not raise
        set_terminal_title("Hello")

    def test_skipped_when_not_tty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        written: list[str] = []
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        monkeypatch.setattr(sys.stdout, "write", written.append)
        monkeypatch.setattr(sys.stdout, "flush", lambda: None)

        set_terminal_title("Hello")

        assert written == []

    def test_skipped_in_pytest_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        written: list[str] = []
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "write", written.append)
        monkeypatch.setattr(sys.stdout, "flush", lambda: None)

        # PYTEST_CURRENT_TEST is already set by the runner; leave it in place
        set_terminal_title("Hello")

        assert written == []

    def test_skipped_when_empty_after_sanitize(self, monkeypatch: pytest.MonkeyPatch) -> None:
        written: list[str] = []
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "write", written.append)
        monkeypatch.setattr(sys.stdout, "flush", lambda: None)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        set_terminal_title("\x00\x1b\x7f")

        # Falls back to "Tau" internally
        assert written == ["\x1b]0;Tau\x07"]
