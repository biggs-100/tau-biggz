from datetime import UTC, datetime
from pathlib import Path

import pytest

from tau_agent import (
    AssistantMessage,
    BranchSummaryEntry,
    CompactionEntry,
    CustomEntry,
    LabelEntry,
    LeafEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionInfoEntry,
    ThinkingLevelChangeEntry,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
from tau_coding.session_export import (
    SessionExportError,
    _active_leaf_id,
    _resolve_export_destination,
    export_session_html,
    normalize_export_format,
    render_session_html,
)


def test_render_session_html_preserves_branch_tree() -> None:
    entries = [
        MessageEntry(id="root", message=UserMessage(content="Start <session>")),
        MessageEntry(
            id="left",
            parent_id="root",
            message=AssistantMessage(content="Left branch"),
        ),
        MessageEntry(
            id="right",
            parent_id="root",
            message=AssistantMessage(
                content="Right branch",
                tool_calls=[ToolCall(id="call-1", name="read", arguments={"path": "README.md"})],
            ),
        ),
        MessageEntry(
            id="tool",
            parent_id="right",
            message=ToolResultMessage(
                tool_call_id="call-1",
                name="read",
                content="File contents",
                ok=True,
                data={"bytes": 13},
            ),
        ),
        CompactionEntry(
            id="compact",
            parent_id="tool",
            summary="The right branch was compacted.",
            replaces_entry_ids=["root", "right", "tool"],
        ),
        LeafEntry(id="leaf", parent_id="compact", entry_id="compact"),
    ]

    html = render_session_html(entries, title="Test Export", source="/tmp/session.jsonl")

    assert "<title>Test Export</title>" in html
    assert "Source: <code>/tmp/session.jsonl</code>" in html
    assert 'id="entry-root"' in html
    assert 'id="entry-left"' in html
    assert 'id="entry-right"' in html
    assert 'id="entry-compact"' in html
    assert "Start &lt;session&gt;" in html
    assert "Right branch [read]" in html
    assert "active-path" in html
    assert "active-leaf" in html
    assert "Replaces entries" in html


def test_export_session_html_writes_file(tmp_path: Path) -> None:
    entries = [MessageEntry(id="root", message=UserMessage(content="Hello"))]
    output_path = tmp_path / "session.html"

    result = export_session_html(entries, output_path, title="Session")

    assert result == output_path
    assert output_path.read_text(encoding="utf-8").startswith("<!doctype html>")


# ── Entry-type rendering tests ───────────────────────────────────────────────


def test_render_model_change_entry() -> None:
    """ModelChangeEntry renders model name and tree-node title."""
    entries = [
        MessageEntry(id="root", message=UserMessage(content="Start")),
        ModelChangeEntry(id="mc1", parent_id="root", model="claude-sonnet-4-20250514"),
    ]
    html = render_session_html(entries)

    # body text
    assert "Model changed to" in html
    assert "<code>claude-sonnet-4-20250514</code>" in html
    # tree-node title
    assert "model change" in html
    # summary in tree
    assert "claude-sonnet-4-20250514" in html


def test_render_thinking_level_change_entry_with_level() -> None:
    """ThinkingLevelChangeEntry renders the level name when set."""
    entries = [
        MessageEntry(id="root", message=UserMessage(content="Start")),
        ThinkingLevelChangeEntry(id="tl1", parent_id="root", thinking_level="high"),
    ]
    html = render_session_html(entries)

    assert "Thinking level changed to" in html
    assert "<code>high</code>" in html
    assert "thinking level change" in html


def test_render_thinking_level_change_entry_none() -> None:
    """ThinkingLevelChangeEntry shows 'off' when thinking_level is None."""
    entries = [
        MessageEntry(id="root", message=UserMessage(content="Start")),
        ThinkingLevelChangeEntry(id="tl2", parent_id="root", thinking_level=None),
    ]
    html = render_session_html(entries)

    assert "Thinking level changed to" in html
    assert "<code>off</code>" in html


def test_render_branch_summary_entry() -> None:
    """BranchSummaryEntry renders branch root and summary body."""
    entries = [
        MessageEntry(id="root", message=UserMessage(content="Start")),
        BranchSummaryEntry(
            id="bs1",
            parent_id="root",
            summary="Merged feature-x changes.",
            branch_root_id="branch-1",
        ),
    ]
    html = render_session_html(entries)

    assert "Branch root:" in html
    assert "<code>branch-1</code>" in html
    assert "Merged feature-x changes." in html
    assert "branch summary" in html


def test_render_label_entry() -> None:
    """LabelEntry renders the session label text."""
    entries = [
        MessageEntry(id="root", message=UserMessage(content="Start")),
        LabelEntry(id="lbl1", parent_id="root", label="v1.0 release"),
    ]
    html = render_session_html(entries)

    assert "Session label:" in html
    assert "<strong>v1.0 release</strong>" in html
    assert "label" in html  # tree-node title


def test_render_session_info_entry() -> None:
    """SessionInfoEntry renders title, working directory, and created timestamp."""
    entries = [
        SessionInfoEntry(
            id="info1",
            title="My Session",
            cwd="/home/user/project",
            created_at=1000000000.0,
        ),
    ]
    expected_ts = datetime.fromtimestamp(1000000000, tz=UTC).replace(microsecond=0).isoformat()
    html = render_session_html(entries)

    assert "<strong>My Session</strong>" in html
    assert "<code>/home/user/project</code>" in html
    assert expected_ts in html
    assert "session info" in html  # tree-node title


def test_render_custom_entry() -> None:
    """CustomEntry renders namespace and serialised data."""
    entries = [
        MessageEntry(id="root", message=UserMessage(content="Start")),
        CustomEntry(
            id="cust1",
            parent_id="root",
            namespace="my-ext",
            data={"key": "value", "count": 42},
        ),
    ]
    html = render_session_html(entries)

    assert "<code>my-ext</code>" in html
    assert "custom:my-ext" in html  # tree-node title
    assert '"key"' in html
    assert '"value"' in html
    assert "2 field(s)" in html  # summary in tree


# ── Message rendering edge cases ─────────────────────────────────────────────


def test_render_assistant_message_no_content() -> None:
    """AssistantMessage with empty content shows fallback text."""
    entries = [
        MessageEntry(
            id="msg1",
            message=AssistantMessage(content=""),
        ),
    ]
    html = render_session_html(entries)

    assert "(no assistant text)" in html
    assert '<p class="message-role">assistant</p>' in html


def test_render_tool_result_with_data_and_details() -> None:
    """ToolResultMessage renders data/details sections when present."""
    entries = [
        MessageEntry(id="root", message=UserMessage(content="Start")),
        MessageEntry(
            id="tool1",
            parent_id="root",
            message=ToolResultMessage(
                tool_call_id="call-1",
                name="read_file",
                content="Operation succeeded.",
                ok=True,
                data={"size": 1024, "lines": 42},
                details={"elapsed_ms": 15},
            ),
        ),
    ]
    html = render_session_html(entries)

    # data section
    assert "<h4>Data</h4>" in html
    assert '"size"' in html
    assert '"lines"' in html
    # details section
    assert "<h4>Details</h4>" in html
    assert '"elapsed_ms"' in html
    # summary in tree
    assert "read_file: Operation succeeded." in html
    # role
    assert '<p class="message-role">tool result</p>' in html


# ── _resolve_export_destination tests ────────────────────────────────────────


def test_resolve_export_destination_no_suffix_no_session_path(tmp_path: Path) -> None:
    """When destination is a directory (no suffix) and session_path is None."""
    result = _resolve_export_destination(
        destination=tmp_path / "output",
        cwd=tmp_path,
        session_path=None,
        format="html",
    )
    assert result == tmp_path / "output" / "tau-session.html"


def test_resolve_export_destination_none_with_session_path(tmp_path: Path) -> None:
    """When destination is None and session_path is set."""
    result = _resolve_export_destination(
        destination=None,
        cwd=tmp_path,
        session_path=tmp_path / "mysession.jsonl",
        format="html",
    )
    assert result == tmp_path / "mysession.html"


def test_resolve_export_destination_none_no_session_path(tmp_path: Path) -> None:
    """When destination is None and session_path is also None."""
    result = _resolve_export_destination(
        destination=None,
        cwd=tmp_path,
        session_path=None,
        format="html",
    )
    assert result == tmp_path / "tau-session.html"


def test_resolve_export_destination_with_suffix(tmp_path: Path) -> None:
    """When destination already has a suffix, return it as-is."""
    result = _resolve_export_destination(
        destination=tmp_path / "my-export.html",
        cwd=tmp_path,
        session_path=None,
        format="html",
    )
    assert result == tmp_path / "my-export.html"


# ── normalize_export_format tests ────────────────────────────────────────────


def test_normalize_export_format_html_variants() -> None:
    """All HTML variants normalise to 'html'."""
    assert normalize_export_format("html") == "html"
    assert normalize_export_format("htm") == "html"
    assert normalize_export_format(".html") == "html"
    assert normalize_export_format("  html  ") == "html"
    assert normalize_export_format("HTML") == "html"
    assert normalize_export_format("HTM") == "html"


def test_normalize_export_format_jsonl() -> None:
    """JSONL variants normalise to 'jsonl'."""
    assert normalize_export_format("jsonl") == "jsonl"
    assert normalize_export_format(".jsonl") == "jsonl"


def test_normalize_export_format_none_and_empty() -> None:
    """None and empty string default to 'html'."""
    assert normalize_export_format(None) == "html"
    assert normalize_export_format("") == "html"


def test_normalize_export_format_invalid() -> None:
    """Unsupported formats raise SessionExportError."""
    with pytest.raises(SessionExportError, match="Unsupported export format: pdf"):
        normalize_export_format("pdf")
    with pytest.raises(SessionExportError, match="Unsupported export format: docx"):
        normalize_export_format("docx")


# ── _active_leaf_id tests ────────────────────────────────────────────────────


def test_active_leaf_id_no_leaf_entry() -> None:
    """Without any LeafEntry, returns the id of the last entry."""
    entries = [
        MessageEntry(id="a", message=UserMessage(content="First")),
        MessageEntry(id="b", parent_id="a", message=UserMessage(content="Second")),
    ]
    assert _active_leaf_id(entries) == "b"


def test_active_leaf_id_empty() -> None:
    """With no entries at all, returns None."""
    assert _active_leaf_id([]) is None


def test_active_leaf_id_with_leaf_entry() -> None:
    """When a LeafEntry exists, returns its entry_id."""
    entries = [
        MessageEntry(id="root", message=UserMessage(content="Start")),
        LeafEntry(id="leaf1", parent_id="root", entry_id="root"),
    ]
    assert _active_leaf_id(entries) == "root"
