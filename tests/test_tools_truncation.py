"""Tests for output-truncation helpers in tau_coding.tools_truncation.

Covers all four public/private functions plus the internal helper:
- _split_lines_for_counting
- _truncate_string_to_bytes_from_end
- truncate_head
- truncate_tail
- format_size
- append_status_block
- _truncation_result
"""

from __future__ import annotations

import pytest

from tau_coding.tools_truncation import (
    _split_lines_for_counting,
    _truncate_string_to_bytes_from_end,
    _truncation_result,
    append_status_block,
    format_size,
    truncate_head,
    truncate_tail,
)
from tau_coding.tools_types import TruncationResult

# ---------------------------------------------------------------------------
# _split_lines_for_counting
# ---------------------------------------------------------------------------


class TestSplitLinesForCounting:
    """_split_lines_for_counting: line splitting without allocation overhead."""

    def test_empty_string(self) -> None:
        assert _split_lines_for_counting("") == []

    def test_single_line_no_trailing_newline(self) -> None:
        assert _split_lines_for_counting("hello") == ["hello"]

    def test_trailing_newline_is_stripped(self) -> None:
        assert _split_lines_for_counting("hello\n") == ["hello"]

    def test_multiple_lines_no_trailing_newline(self) -> None:
        assert _split_lines_for_counting("a\nb\nc") == ["a", "b", "c"]

    def test_multiple_lines_with_trailing_newline(self) -> None:
        assert _split_lines_for_counting("a\nb\nc\n") == ["a", "b", "c"]

    def test_only_newlines(self) -> None:
        assert _split_lines_for_counting("\n\n") == ["", ""]


# ---------------------------------------------------------------------------
# _truncate_string_to_bytes_from_end
# ---------------------------------------------------------------------------


class TestTruncateStringToBytesFromEnd:
    """Byte-level tail clipping on a single string."""

    def test_within_max_bytes_returns_unchanged(self) -> None:
        assert _truncate_string_to_bytes_from_end("hello", 100) == "hello"

    def test_exact_max_bytes_returns_unchanged(self) -> None:
        assert _truncate_string_to_bytes_from_end("hello", 5) == "hello"

    def test_clips_tail_when_oversized(self) -> None:
        result = _truncate_string_to_bytes_from_end("hello world", 5)
        assert result == "world"

    def test_short_max_bytes(self) -> None:
        result = _truncate_string_to_bytes_from_end("abcdef", 2)
        assert result == "ef"

    def test_multi_byte_unicode_does_not_crash(self) -> None:
        """UTF-8 multi-byte characters clipped mid-sequence survive decode."""
        text = "a😀b"  # U+1F600 → 4 UTF-8 bytes
        result = _truncate_string_to_bytes_from_end(text, 3)
        assert isinstance(result, str)

    def test_empty_string(self) -> None:
        assert _truncate_string_to_bytes_from_end("", 100) == ""


# ---------------------------------------------------------------------------
# _truncation_result (internal helper)
# ---------------------------------------------------------------------------


class TestTruncationResult:
    """_truncation_result builds a frozen TruncationResult dataclass."""

    def test_minimal_args(self) -> None:
        result = _truncation_result(
            content="hello",
            truncated=True,
            truncated_by="bytes",
            total_lines=5,
            total_bytes=100,
            output_lines=1,
            output_bytes=5,
        )
        assert isinstance(result, TruncationResult)
        assert result.content == "hello"
        assert result.truncated is True
        assert result.truncated_by == "bytes"
        assert result.total_lines == 5
        assert result.total_bytes == 100
        assert result.output_lines == 1
        assert result.output_bytes == 5
        assert result.last_line_partial is False
        assert result.first_line_exceeds_limit is False
        assert result.max_lines == 2000
        assert result.max_bytes == 51200

    def test_with_optional_flags(self) -> None:
        result = _truncation_result(
            content="",
            truncated=True,
            truncated_by="bytes",
            total_lines=1,
            total_bytes=200,
            output_lines=0,
            output_bytes=0,
            last_line_partial=True,
            first_line=True,
        )
        assert result.last_line_partial is True
        assert result.first_line_exceeds_limit is True


# ---------------------------------------------------------------------------
# truncate_head
# ---------------------------------------------------------------------------


class TestTruncateHead:
    """truncate_head: keep first N lines/bytes from the front."""

    def test_empty_content_not_truncated(self) -> None:
        result = truncate_head("")
        assert result.truncated is False
        assert result.content == ""
        assert result.total_lines == 0

    def test_content_fits_no_truncation(self) -> None:
        text = "hello\nworld"
        result = truncate_head(text, max_lines=10, max_bytes=10_000)
        assert result.truncated is False
        assert result.content == text
        assert result.total_lines == 2

    def test_first_line_exceeds_max_bytes_returns_empty(self) -> None:
        """Byte-level: if even the first line is too big, return empty."""
        text = "x" * 200
        result = truncate_head(text, max_lines=10, max_bytes=100)
        assert result.truncated is True
        assert result.truncated_by == "bytes"
        assert result.content == ""
        assert result.first_line_exceeds_limit is True
        assert result.output_lines == 0
        assert result.output_bytes == 0

    def test_truncated_by_max_lines(self) -> None:
        text = "line1\nline2\nline3\nline4"
        result = truncate_head(text, max_lines=2, max_bytes=10_000)
        assert result.truncated is True
        assert result.truncated_by == "lines"
        assert result.content == "line1\nline2"
        assert result.total_lines == 4
        assert result.output_lines == 2

    def test_truncated_by_bytes_during_iteration(self) -> None:
        """Content within max_lines but second line pushes past max_bytes."""
        text = "a\n" + "b" * 100
        result = truncate_head(text, max_lines=10, max_bytes=50)
        assert result.truncated is True
        assert result.truncated_by == "bytes"
        assert result.content == "a"
        assert result.output_lines == 1

    def test_exact_boundary_no_truncation(self) -> None:
        text = "hello\nworld"
        result = truncate_head(text, max_lines=2, max_bytes=100)
        assert result.truncated is False
        assert result.content == text

    def test_newline_byte_counting_in_budget(self) -> None:
        """Newline separators consume bytes from the budget."""
        text = "a\n" + "b" * 100
        result = truncate_head(text, max_lines=10, max_bytes=5)
        assert result.truncated is True
        assert result.truncated_by == "bytes"
        assert result.content == "a"


# ---------------------------------------------------------------------------
# truncate_tail
# ---------------------------------------------------------------------------


class TestTruncateTail:
    """truncate_tail: keep last N lines/bytes from the end."""

    def test_empty_content_not_truncated(self) -> None:
        result = truncate_tail("")
        assert result.truncated is False
        assert result.content == ""

    def test_content_fits_no_truncation(self) -> None:
        text = "hello\nworld"
        result = truncate_tail(text, max_lines=10, max_bytes=10_000)
        assert result.truncated is False
        assert result.content == text

    def test_truncated_by_max_lines(self) -> None:
        text = "line1\nline2\nline3\nline4\nline5\nline6"
        result = truncate_tail(text, max_lines=3, max_bytes=10_000)
        assert result.truncated is True
        assert result.truncated_by == "lines"
        assert result.content == "line4\nline5\nline6"
        assert result.output_lines == 3

    def test_partial_line_clip_when_last_line_exceeds_max_bytes(self) -> None:
        """First (from-end) line too big → clipped, last_line_partial=True."""
        long_line = "x" * 200
        result = truncate_tail(long_line, max_lines=10, max_bytes=100)
        assert result.truncated is True
        assert result.truncated_by == "bytes"
        assert result.last_line_partial is True
        assert len(result.content) < len(long_line)
        assert result.output_lines == 1

    def test_bytes_overflow_without_partial_line_clip(self) -> None:
        """Previous lines already in output → no clip, just break."""
        text = "a" * 100 + "\nb\nc"
        result = truncate_tail(text, max_lines=10, max_bytes=70)
        assert result.truncated is True
        assert result.truncated_by == "bytes"
        assert result.last_line_partial is False
        # "c" and "b" fit, "a"*100 doesn't → output is "b\nc"
        assert result.content == "b\nc"
        assert result.output_lines == 2

    def test_max_lines_limit_exceeded(self) -> None:
        """max_lines capping from the tail end."""
        text = "\n".join(f"line{i}" for i in range(10))
        result = truncate_tail(text, max_lines=3, max_bytes=10_000)
        assert result.truncated is True
        assert result.truncated_by == "lines"
        assert result.content == "line7\nline8\nline9"
        assert result.output_lines == 3

    def test_partial_line_with_multibyte_unicode(self) -> None:
        """Partial clip path does not crash on multi-byte characters."""
        text = "😀" * 50  # 4 bytes each = 200 bytes
        result = truncate_tail(text, max_lines=10, max_bytes=50)
        assert result.truncated is True
        assert result.last_line_partial is True
        assert result.output_lines == 1


# ---------------------------------------------------------------------------
# format_size
# ---------------------------------------------------------------------------


class TestFormatSize:
    """format_size: human-readable byte sizes."""

    @pytest.mark.parametrize(
        ("byte_count", "expected"),
        [
            (0, "0B"),
            (1, "1B"),
            (512, "512B"),
            (1023, "1023B"),
            (1024, "1.0KB"),
            (1025, "1.0KB"),
            (1536, "1.5KB"),
            (10240, "10.0KB"),
            (51200, "50.0KB"),
            (1048576, "1.0MB"),
            (2097152, "2.0MB"),
            (1572864, "1.5MB"),
        ],
    )
    def test_format_size(self, byte_count: int, expected: str) -> None:
        assert format_size(byte_count) == expected


# ---------------------------------------------------------------------------
# append_status_block
# ---------------------------------------------------------------------------


class TestAppendStatusBlock:
    """append_status_block: command-status suffix."""

    def test_content_exists(self) -> None:
        assert append_status_block("output", "status") == "output\n\nstatus"

    def test_empty_content(self) -> None:
        assert append_status_block("", "status") == "status"
