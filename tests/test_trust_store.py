"""Tests for the trust store persistence layer and ask-message formatting."""

from __future__ import annotations

import json
from pathlib import Path

from tau_coding.trust_store import TrustStore, format_ask_message

# ── TrustStore load/save tests ─────────────────────────────────────────────


def test_load_no_file(tmp_path: Path) -> None:
    """TrustStore.load() returns empty when trust.json does not exist."""
    store = TrustStore.load(data_dir=tmp_path)
    assert store.trusted_tools == set()


def test_load_valid_file(tmp_path: Path) -> None:
    """TrustStore.load() parses valid JSON correctly."""
    trust_file = tmp_path / "trust.json"
    trust_file.write_text(json.dumps({"version": 1, "trusted_tools": ["bash"]}), encoding="utf-8")
    store = TrustStore.load(data_dir=tmp_path)
    assert store.is_trusted("bash") is True
    assert store.is_trusted("write") is False


def test_load_corrupted_file(tmp_path: Path) -> None:
    """TrustStore.load() handles invalid JSON gracefully (returns empty)."""
    trust_file = tmp_path / "trust.json"
    trust_file.write_text("not valid json", encoding="utf-8")
    store = TrustStore.load(data_dir=tmp_path)
    assert store.trusted_tools == set()


def test_load_not_a_dict(tmp_path: Path) -> None:
    """TrustStore.load() treats non-dict JSON as empty."""
    trust_file = tmp_path / "trust.json"
    trust_file.write_text(json.dumps(["bash"]), encoding="utf-8")
    store = TrustStore.load(data_dir=tmp_path)
    assert store.trusted_tools == set()


def test_save_and_reload(tmp_path: Path) -> None:
    """TrustStore.save() writes canonical JSON that load() can read back."""
    store = TrustStore(trusted_tools={"bash", "read"}, data_dir=tmp_path)
    store.save()

    loaded = TrustStore.load(data_dir=tmp_path)
    assert loaded.trusted_tools == {"bash", "read"}
    assert loaded.version == 1

    # Verify file content with sorted tools
    raw = json.loads((tmp_path / "trust.json").read_text(encoding="utf-8"))
    assert raw == {"version": 1, "trusted_tools": ["bash", "read"]}


def test_add_is_trusted(tmp_path: Path) -> None:
    """TrustStore.add() adds a tool and is_trusted() returns True."""
    store = TrustStore(data_dir=tmp_path)
    result = store.add("bash")
    assert result is True
    assert store.is_trusted("bash") is True


def test_add_duplicate(tmp_path: Path) -> None:
    """TrustStore.add() called twice returns False the second time."""
    store = TrustStore(data_dir=tmp_path)
    store.add("bash")
    result = store.add("bash")
    assert result is False


def test_remove(tmp_path: Path) -> None:
    """TrustStore.remove() removes a tool and returns True."""
    store = TrustStore(data_dir=tmp_path)
    store.add("bash")
    result = store.remove("bash")
    assert result is True
    assert store.is_trusted("bash") is False


def test_remove_nonexistent(tmp_path: Path) -> None:
    """TrustStore.remove() for untrusted tool returns False."""
    store = TrustStore(data_dir=tmp_path)
    result = store.remove("nonexistent")
    assert result is False


def test_persistence_across_loads(tmp_path: Path) -> None:
    """Trust persists across multiple load() calls."""
    store = TrustStore(data_dir=tmp_path)
    store.add("bash")
    store.add("read")

    loaded = TrustStore.load(data_dir=tmp_path)
    assert loaded.trusted_tools == {"bash", "read"}

    loaded.remove("bash")
    loaded.save()

    reloaded = TrustStore.load(data_dir=tmp_path)
    assert reloaded.trusted_tools == {"read"}


def test_list_trusted(tmp_path: Path) -> None:
    """TrustStore.list_trusted() returns the set of tool names."""
    store = TrustStore(trusted_tools={"bash", "read"}, data_dir=tmp_path)
    assert store.list_trusted() == {"bash", "read"}


# ── format_ask_message tests ───────────────────────────────────────────────


def test_format_ask_message_no_args() -> None:
    """format_ask_message without args omits the Args: segment."""
    msg = format_ask_message("bash")
    assert "Tool 'bash' requires your approval." in msg
    assert "Use /trust add bash to trust it." in msg
    assert "Args:" not in msg


def test_format_ask_message_with_args() -> None:
    """format_ask_message with args includes the Args: segment."""
    msg = format_ask_message("bash", {"command": "echo hello"})
    assert "Args: command=echo hello." in msg


def test_arg_format_truncation() -> None:
    """Long values are truncated to 60 characters."""
    long_val = "a" * 100
    msg = format_ask_message("bash", {"command": long_val})
    assert "Args:" in msg
    # 57 chars + "..."
    assert "..." in msg
    assert len(long_val) not in [len(line) for line in msg.split("\n") if "a" in line]
    assert "aaaaaaaaa" in msg


def test_arg_format_max_3_args() -> None:
    """Only first 3 argument pairs are shown, 4th+ omitted."""
    args = {
        "a": "1",
        "b": "2",
        "c": "3",
        "d": "4",
    }
    msg = format_ask_message("tool", args)
    assert "a=1" in msg
    assert "b=2" in msg
    assert "c=3" in msg
    assert "d=4" not in msg


def test_format_ask_message_empty_args() -> None:
    """Empty dict arguments produce no Args: segment."""
    msg = format_ask_message("bash", {})
    assert "Args:" not in msg


def test_format_ask_message_none_args() -> None:
    """None arguments produce no Args: segment."""
    msg = format_ask_message("bash", None)
    assert "Args:" not in msg
