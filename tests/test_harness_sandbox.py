"""Tests for [sandbox] section parsing in harness TOML files."""

from __future__ import annotations

from pathlib import Path

from tau_coding.harness import _parse_harness_file


class TestParseSandboxSection:
    """TOML [sandbox] section parsing."""

    def test_parse_full_sandbox_section(self, tmp_path: Path) -> None:
        """Full [sandbox] section is parsed correctly."""
        hfile = tmp_path / ".tau" / "harnesses" / "sandboxed.toml"
        hfile.parent.mkdir(parents=True)
        hfile.write_text("""
name = "sandboxed"
description = "Sandboxed harness"

[personality]
system_prompt = "You are sandboxed."

[sandbox]
mode = "strict"
allowed_paths = ["/data", "../other-project"]
allow_home_tau = false
allow_temp = false
""")
        h = _parse_harness_file(hfile)
        assert h.sandbox.mode == "strict"
        assert h.sandbox.allowed_paths == ("/data", "../other-project")
        assert h.sandbox.allow_home_tau is False
        assert h.sandbox.allow_temp is False

    def test_parse_missing_sandbox_section(self, tmp_path: Path) -> None:
        """No [sandbox] section yields permissive defaults."""
        hfile = tmp_path / ".tau" / "harnesses" / "plain.toml"
        hfile.parent.mkdir(parents=True)
        hfile.write_text("""
name = "plain"
description = "Plain harness"

[personality]
system_prompt = "You are plain."
""")
        h = _parse_harness_file(hfile)
        assert h.sandbox.mode == "permissive"
        assert h.sandbox.allowed_paths == ()
        assert h.sandbox.allow_home_tau is True
        assert h.sandbox.allow_temp is True

    def test_parse_partial_sandbox_section(self, tmp_path: Path) -> None:
        """Partial [sandbox] uses defaults for missing fields."""
        hfile = tmp_path / ".tau" / "harnesses" / "partial.toml"
        hfile.parent.mkdir(parents=True)
        hfile.write_text("""
name = "partial"
description = "Partial sandbox"

[personality]
system_prompt = "You are partial."

[sandbox]
mode = "strict"
""")
        h = _parse_harness_file(hfile)
        assert h.sandbox.mode == "strict"
        assert h.sandbox.allowed_paths == ()
        assert h.sandbox.allow_home_tau is True
        assert h.sandbox.allow_temp is True
