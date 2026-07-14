"""Tests for tau_coding.tools_edit — file-edit helper functions.

Covers all pure functions in the module: line-ending detection, edit-argument
preparation, edit parsing, overlap validation, content application, diff
generation, and error-message helpers.
"""

from __future__ import annotations

import pytest

from tau_coding.tools_edit import (
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
from tau_coding.tools_types import ToolInputError

# ── detect_line_ending ─────────────────────────────────────────────────


class TestDetectLineEnding:
    def test_crlf_only(self) -> None:
        assert detect_line_ending("line1\r\nline2\r\n") == "\r\n"

    def test_lf_only(self) -> None:
        assert detect_line_ending("line1\nline2\n") == "\n"

    def test_no_newlines(self) -> None:
        assert detect_line_ending("single line") == "\n"

    def test_mixed_crlf_first(self) -> None:
        """CRLF appears before the first bare LF → prefer CRLF."""
        assert detect_line_ending("\r\nfirst\nsecond") == "\r\n"

    def test_mixed_lf_first(self) -> None:
        """Bare LF appears before the first CRLF → prefer LF."""
        assert detect_line_ending("\nfirst\r\nsecond") == "\n"

    def test_cr_only(self) -> None:
        assert detect_line_ending("line1\rline2\r") == "\n"


# ── normalize_to_lf / restore_line_endings ────────────────────────────────


class TestNormalizeRestore:
    def test_normalize_crlf_to_lf(self) -> None:
        assert normalize_to_lf("a\r\nb\r\nc") == "a\nb\nc"

    def test_normalize_cr_to_lf(self) -> None:
        assert normalize_to_lf("a\rb\rc") == "a\nb\nc"

    def test_normalize_mixed(self) -> None:
        assert normalize_to_lf("a\r\nb\rc\n") == "a\nb\nc\n"

    def test_restore_to_crlf(self) -> None:
        assert restore_line_endings("a\nb\nc", "\r\n") == "a\r\nb\r\nc"

    def test_restore_to_lf_is_identity(self) -> None:
        assert restore_line_endings("a\nb\nc", "\n") == "a\nb\nc"


# ── _strip_bom ─────────────────────────────────────────────────────────


class TestStripBOM:
    def test_with_bom(self) -> None:
        bom, rest = _strip_bom("\ufeffhello")
        assert bom == "\ufeff"
        assert rest == "hello"

    def test_without_bom(self) -> None:
        bom, rest = _strip_bom("hello")
        assert bom == ""
        assert rest == "hello"

    def test_empty_string(self) -> None:
        bom, rest = _strip_bom("")
        assert bom == ""
        assert rest == ""


# ── _prepare_edit_arguments ────────────────────────────────────────────


class TestPrepareEditArguments:
    def test_passthrough_when_no_edits_or_legacy(self) -> None:
        result = _prepare_edit_arguments({"path": "foo.txt"})
        assert result == {"path": "foo.txt"}

    def test_parses_edits_json_string(self) -> None:
        result = _prepare_edit_arguments({"edits": '[{"oldText": "a", "newText": "b"}]'})
        assert result["edits"] == [{"oldText": "a", "newText": "b"}]

    def test_ignores_invalid_edits_json_string(self) -> None:
        """Invalid JSON leaves the string value as-is."""
        result = _prepare_edit_arguments({"edits": "not-json"})
        assert result["edits"] == "not-json"

    def test_ignores_non_array_json(self) -> None:
        """JSON object is not a list — leaves the string as-is."""
        result = _prepare_edit_arguments({"edits": '{"a": 1}'})
        assert result["edits"] == '{"a": 1}'

    def test_merges_legacy_oldtext_newtext(self) -> None:
        result = _prepare_edit_arguments({"oldText": "foo", "newText": "bar"})
        assert result["edits"] == [{"oldText": "foo", "newText": "bar"}]
        assert "oldText" not in result
        assert "newText" not in result

    def test_merges_legacy_into_existing_edits(self) -> None:
        result = _prepare_edit_arguments(
            {
                "edits": [{"oldText": "a", "newText": "b"}],
                "oldText": "c",
                "newText": "d",
            }
        )
        assert result["edits"] == [
            {"oldText": "a", "newText": "b"},
            {"oldText": "c", "newText": "d"},
        ]

    def test_merges_legacy_with_non_list_edits(self) -> None:
        """If edits exists but isn't a list, treat it as empty and merge."""
        result = _prepare_edit_arguments({"edits": "string", "oldText": "a", "newText": "b"})
        assert result["edits"] == [{"oldText": "a", "newText": "b"}]

    def test_does_not_merge_partial_legacy(self) -> None:
        """Both oldText and newText must be strings to trigger merging."""
        result = _prepare_edit_arguments({"oldText": "foo"})
        assert "edits" not in result
        assert result.get("oldText") == "foo"


# ── _edits_arg ─────────────────────────────────────────────────────────


class TestEditsArg:
    def test_valid_edits(self) -> None:
        result = _edits_arg({"edits": [{"oldText": "a", "newText": "b"}]})
        assert result == [{"oldText": "a", "newText": "b"}]

    def test_missing_edits_key(self) -> None:
        with pytest.raises(ToolInputError, match="edits must contain at least one"):
            _edits_arg({})

    def test_edits_not_a_list(self) -> None:
        with pytest.raises(ToolInputError, match="edits must contain at least one"):
            _edits_arg({"edits": "string"})

    def test_edits_empty_list(self) -> None:
        with pytest.raises(ToolInputError, match="edits must contain at least one"):
            _edits_arg({"edits": []})

    def test_non_dict_item(self) -> None:
        with pytest.raises(ToolInputError, match=r"edits\[0\] must be an object"):
            _edits_arg({"edits": ["string"]})

    def test_missing_oldtext(self) -> None:
        with pytest.raises(
            ToolInputError, match=r"edits\[0\].oldText and edits\[0\].newText must be strings"
        ):
            _edits_arg({"edits": [{"newText": "b"}]})

    def test_missing_newtext(self) -> None:
        with pytest.raises(
            ToolInputError, match=r"edits\[0\].oldText and edits\[0\].newText must be strings"
        ):
            _edits_arg({"edits": [{"oldText": "a"}]})

    def test_non_string_oldtext(self) -> None:
        with pytest.raises(
            ToolInputError, match=r"edits\[0\].oldText and edits\[0\].newText must be strings"
        ):
            _edits_arg({"edits": [{"oldText": 42, "newText": "b"}]})

    @pytest.mark.parametrize("index", [0, 1])
    def test_second_item_invalid(self, index: int) -> None:
        items = [{"oldText": "a", "newText": "b"}, {"oldText": "x", "newText": "y"}]
        items[index] = "not-a-dict"
        with pytest.raises(ToolInputError, match=rf"edits\[{index}\] must be an object"):
            _edits_arg({"edits": items})


# ── _validate_non_overlapping ──────────────────────────────────────────


class TestValidateNonOverlapping:
    def test_single_span(self) -> None:
        """Single span always passes."""
        _validate_non_overlapping([(0, 5, "new")])

    def test_non_overlapping_sorted(self) -> None:
        _validate_non_overlapping([(0, 3, "a"), (3, 6, "b")])

    def test_non_overlapping_unsorted_order(self) -> None:
        """Validation sorts internally — order doesn't matter."""
        _validate_non_overlapping([(3, 6, "a"), (0, 3, "b")])

    def test_non_overlapping_with_gap(self) -> None:
        _validate_non_overlapping([(0, 2, "a"), (5, 8, "b")])

    def test_overlapping_adjacent(self) -> None:
        """Spans [0, 5) and [3, 8) overlap."""
        with pytest.raises(ToolInputError, match="Edits must not overlap"):
            _validate_non_overlapping([(0, 5, "a"), (3, 8, "b")])

    def test_overlapping_identical(self) -> None:
        with pytest.raises(ToolInputError, match="Edits must not overlap"):
            _validate_non_overlapping([(2, 6, "a"), (2, 6, "b")])

    def test_nested_span(self) -> None:
        """[0, 10) fully contains [3, 7)."""
        with pytest.raises(ToolInputError, match="Edits must not overlap"):
            _validate_non_overlapping([(0, 10, "a"), (3, 7, "b")])


# ── _count_occurrences ─────────────────────────────────────────────────


class TestCountOccurrences:
    def test_zero_occurrences(self) -> None:
        assert _count_occurrences("hello world", "xyz") == 0

    def test_one_occurrence(self) -> None:
        assert _count_occurrences("hello world", "world") == 1

    def test_multiple_occurrences(self) -> None:
        assert _count_occurrences("abc abc abc", "abc") == 3

    def test_overlapping_not_counted(self) -> None:
        """The implementation does not count overlapping matches."""
        assert _count_occurrences("aaa", "aa") == 1

    def test_empty_content(self) -> None:
        assert _count_occurrences("", "x") == 0


# ── apply_edits_to_normalized_content ──────────────────────────────────


class TestApplyEditsToNormalizedContent:
    def test_single_edit(self) -> None:
        old, new = apply_edits_to_normalized_content(
            "hello world", [{"oldText": "world", "newText": "there"}], "f.txt"
        )
        assert old == "hello world"
        assert new == "hello there"

    def test_multiple_edits(self) -> None:
        old, new = apply_edits_to_normalized_content(
            "a b c",
            [{"oldText": "a", "newText": "x"}, {"oldText": "c", "newText": "z"}],
            "f.txt",
        )
        assert new == "x b z"

    def test_empty_old_text_raises(self) -> None:
        with pytest.raises(ToolInputError, match="oldText must not be empty"):
            apply_edits_to_normalized_content("content", [{"oldText": "", "newText": "b"}], "f.txt")

    def test_empty_old_text_multi_edit_raises_index(self) -> None:
        with pytest.raises(ToolInputError, match=r"edits\[1\].oldText must not be empty"):
            apply_edits_to_normalized_content(
                "content",
                [{"oldText": "a", "newText": "b"}, {"oldText": "", "newText": "d"}],
                "f.txt",
            )

    def test_not_found_raises(self) -> None:
        with pytest.raises(ToolInputError, match="Could not find"):
            apply_edits_to_normalized_content(
                "hello", [{"oldText": "world", "newText": "x"}], "f.txt"
            )

    def test_duplicate_raises(self) -> None:
        with pytest.raises(ToolInputError, match="Found 2 occurrences"):
            apply_edits_to_normalized_content("x x", [{"oldText": "x", "newText": "y"}], "f.txt")

    def test_no_change_raises(self) -> None:
        with pytest.raises(ToolInputError, match="No changes made"):
            apply_edits_to_normalized_content(
                "same", [{"oldText": "same", "newText": "same"}], "f.txt"
            )

    def test_no_change_multi_edit_raises(self) -> None:
        """Both edits match distinct parts of the content and their net effect
        produces identical content, triggering the no-change error."""
        with pytest.raises(ToolInputError, match="The replacements produced identical content"):
            apply_edits_to_normalized_content(
                "hello world",
                [
                    {"oldText": "hello", "newText": "hello "},
                    {"oldText": " world", "newText": "world"},
                ],
                "f.txt",
            )

    def test_normalizes_line_endings(self) -> None:
        """Normalized oldText (LF-only) matches content that is already LF-only.
        The function normalizes edit texts, so CRLF in the edit still works
        against already-normalized (LF) content.
        """
        old, new = apply_edits_to_normalized_content(
            "hello\nworld",
            [{"oldText": "hello\r\n", "newText": "hi\r\n"}],
            "f.txt",
        )
        assert new == "hi\nworld"


# ── generate_diff_string ──────────────────────────────────────────────


class TestGenerateDiffString:
    def test_no_changes(self) -> None:
        diff, line = generate_diff_string("same", "same")
        assert line is None
        assert isinstance(diff, str)

    def test_addition_first_changed_line(self) -> None:
        """Adding a line before existing content starts at line 1."""
        diff, line = generate_diff_string("world\n", "hello\nworld\n")
        assert line == 1

    def test_removal_first_changed_line(self) -> None:
        """Removing the first line sets first_changed_line to 1."""
        diff, line = generate_diff_string("first\nsecond\n", "second\n")
        assert line == 1

    def test_addition_after_content(self) -> None:
        """Adding after content sets the correct line number."""
        diff, line = generate_diff_string("a\nb\n", "a\nb\nc\n")
        assert line == 3

    def test_removal_mid_content(self) -> None:
        """Removing a middle line gives the line number of the removal."""
        diff, line = generate_diff_string("a\nb\nc\n", "a\nc\n")
        assert line == 2

    def test_replacement(self) -> None:
        diff, line = generate_diff_string("old\n", "new\n")
        assert line == 1

    def test_empty_strings(self) -> None:
        diff, line = generate_diff_string("", "")
        assert line is None

    def test_addition_to_empty(self) -> None:
        diff, line = generate_diff_string("", "hello\n")
        assert line == 1


# ── generate_unified_patch ────────────────────────────────────────────


class TestGenerateUnifiedPatch:
    def test_returns_patch_string(self) -> None:
        patch = generate_unified_patch("f.txt", "a\nb\n", "a\nc\n")
        assert "--- f.txt" in patch
        assert "+++ f.txt" in patch
        assert "-b" in patch
        assert "+c" in patch

    def test_no_changes(self) -> None:
        patch = generate_unified_patch("f.txt", "same\n", "same\n")
        assert patch == ""


# ── Error message helpers ──────────────────────────────────────────────


class TestNotFoundError:
    def test_single_edit(self) -> None:
        msg = _not_found_error("f.txt", 0, 1)
        assert "Could not find the exact text in f.txt" in msg
        assert "edits[0]" not in msg

    def test_multi_edit(self) -> None:
        msg = _not_found_error("f.txt", 1, 3)
        assert "Could not find edits[1] in f.txt" in msg


class TestDuplicateError:
    def test_single_edit(self) -> None:
        msg = _duplicate_error("f.txt", 0, 1, 2)
        assert "Found 2 occurrences of the text in f.txt" in msg

    def test_multi_edit(self) -> None:
        msg = _duplicate_error("f.txt", 2, 5, 3)
        assert "Found 3 occurrences of edits[2] in f.txt" in msg


class TestEmptyOldTextError:
    def test_single_edit(self) -> None:
        msg = _empty_old_text_error("f.txt", 0, 1)
        assert msg == "oldText must not be empty in f.txt."

    def test_multi_edit(self) -> None:
        msg = _empty_old_text_error("f.txt", 1, 3)
        assert msg == "edits[1].oldText must not be empty in f.txt."


class TestNoChangeError:
    def test_single_edit(self) -> None:
        msg = _no_change_error("f.txt", 1)
        assert "No changes made to f.txt." in msg
        assert "The replacement produced identical content." in msg

    def test_multi_edit(self) -> None:
        msg = _no_change_error("f.txt", 3)
        assert msg == "No changes made to f.txt. The replacements produced identical content."


# ── _detect_supported_image_mime_type ──────────────────────────────────


class TestDetectSupportedImageMimeType:
    def test_png(self) -> None:
        from pathlib import Path

        assert _detect_supported_image_mime_type(Path("img.png")) == "image/png"

    def test_jpeg(self) -> None:
        from pathlib import Path

        assert _detect_supported_image_mime_type(Path("photo.jpg")) == "image/jpeg"

    def test_gif(self) -> None:
        from pathlib import Path

        assert _detect_supported_image_mime_type(Path("anim.gif")) == "image/gif"

    def test_webp(self) -> None:
        """WebP detection depends on the platform mimetypes database."""
        from pathlib import Path

        result = _detect_supported_image_mime_type(Path("img.webp"))
        assert result in ("image/webp", None)

    def test_not_supported(self) -> None:
        from pathlib import Path

        assert _detect_supported_image_mime_type(Path("doc.pdf")) is None

    def test_unknown_extension(self) -> None:
        from pathlib import Path

        assert _detect_supported_image_mime_type(Path("unknown.xyz")) is None

    def test_no_extension(self) -> None:
        from pathlib import Path

        assert _detect_supported_image_mime_type(Path("Makefile")) is None


# ── Edge: function-level coverage completion ──────────────────────────


class TestEdgeCoverage:
    """Completes any remaining uncovered branches."""

    def test_detect_line_ending_crlf_index_zero(self) -> None:
        """CRLF at position 0, LF later."""
        assert detect_line_ending("\r\nx\n") == "\r\n"

    def test_detect_line_ending_lf_at_zero(self) -> None:
        """LF at position 0, CRLF later."""
        assert detect_line_ending("\nx\r\n") == "\n"

    def test_prepare_edit_arguments_edits_already_list_gets_json_string(self) -> None:
        """If edits is already a list, the JSON string branch is skipped."""
        result = _prepare_edit_arguments({"edits": [{"oldText": "a", "newText": "b"}]})
        assert result["edits"] == [{"oldText": "a", "newText": "b"}]
