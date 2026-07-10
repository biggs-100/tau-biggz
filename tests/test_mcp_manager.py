"""Tests for tau_coding.mcp_manager — MCP server config management."""

from __future__ import annotations

from pathlib import Path

import pytest

from tau_coding.mcp_manager import (
    _entry_for_package,
    _load_configs,
    _package_to_name,
    _save_configs,
    mcp_install,
    mcp_list,
    mcp_remove,
    mcp_search,
)

# ── helpers ────────────────────────────────────────────────────────────


def _monkeypatch_config_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect _mcp_config_path to tmp_path/.tau/mcp.toml and return the path."""
    config_path = tmp_path / ".tau" / "mcp.toml"
    monkeypatch.setattr(
        "tau_coding.mcp_manager._mcp_config_path",
        lambda: config_path,
    )
    return config_path


# ── _package_to_name ──────────────────────────────────────────────────


class TestPackageToName:
    def test_simple_name(self) -> None:
        assert _package_to_name("server-filesystem") == "filesystem"

    def test_not_server_prefix(self) -> None:
        assert _package_to_name("my-tool") == "my-tool"

    def test_with_npm_scope(self) -> None:
        assert _package_to_name("@scope/server-foo") == "foo"

    def test_with_npm_scope_no_server(self) -> None:
        assert _package_to_name("@scope/my-package") == "my-package"

    def test_already_stripped(self) -> None:
        assert _package_to_name("  server-foo  ") == "foo"

    def test_empty_string(self) -> None:
        assert _package_to_name("") == ""


# ── _entry_for_package ────────────────────────────────────────────────


class TestEntryForPackage:
    def test_basic_entry(self) -> None:
        entry = _entry_for_package("@modelcontextprotocol/server-filesystem", "filesystem")
        assert entry["name"] == "filesystem"
        assert entry["transport"] == "stdio"
        assert entry["command"] == "npx"
        assert entry["args"] == ["-y", "@modelcontextprotocol/server-filesystem"]

    def test_entry_strips_whitespace(self) -> None:
        entry = _entry_for_package("  server-foo  ", "foo")
        assert entry["args"] == ["-y", "server-foo"]


# ── config round-trip ─────────────────────────────────────────────────


class TestConfigIO:
    def test_load_empty_when_no_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _monkeypatch_config_path(monkeypatch, tmp_path)
        assert _load_configs() == []

    def test_save_and_load_round_trip(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _monkeypatch_config_path(monkeypatch, tmp_path)
        configs = [
            {
                "name": "filesystem",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@scope/server-fs"],
            },
            {
                "name": "brave-search",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@scope/server-brave"],
            },
        ]
        _save_configs(configs)
        loaded = _load_configs()
        assert len(loaded) == 2
        assert loaded[0]["name"] == "filesystem"
        assert loaded[0]["command"] == "npx"
        assert loaded[1]["name"] == "brave-search"

    def test_save_and_load_empty_list(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _monkeypatch_config_path(monkeypatch, tmp_path)
        _save_configs([])
        assert _load_configs() == []

    def test_corrupted_toml_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_path = _monkeypatch_config_path(monkeypatch, tmp_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("[[broken toml\ninvalid")
        assert _load_configs() == []

    def test_saved_file_is_readable_toml(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        config_path = _monkeypatch_config_path(monkeypatch, tmp_path)
        configs = [
            {"name": "test", "transport": "stdio", "command": "npx", "args": ["-y", "server-test"]},
        ]
        _save_configs(configs)
        raw = config_path.read_text(encoding="utf-8")
        assert "[[servers]]" in raw
        assert 'name = "test"' in raw
        assert 'command = "npx"' in raw
        assert 'args = ["-y", "server-test"]' in raw


# ── mcp_list ──────────────────────────────────────────────────────────


class TestMcpList:
    def test_list_empty(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _monkeypatch_config_path(monkeypatch, tmp_path)
        assert mcp_list() == []

    def test_list_with_servers(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _monkeypatch_config_path(monkeypatch, tmp_path)
        _save_configs(
            [
                {"name": "fs", "transport": "stdio", "command": "npx", "args": ["-y", "server-fs"]},
                {
                    "name": "search",
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "server-search"],
                },
            ]
        )
        result = mcp_list()
        assert len(result) == 2
        assert result[0]["name"] == "fs"
        assert result[1]["name"] == "search"


# ── mcp_search ────────────────────────────────────────────────────────


class TestMcpSearch:
    def test_search_fallback_on_network_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """mcp_search falls back to a stub result when the network call fails."""
        import httpx

        def _raise(*args: object, **kwargs: object) -> httpx.Response:
            raise httpx.ConnectError("Simulated network error")

        monkeypatch.setattr(httpx, "get", _raise)

        results = mcp_search("filesystem")
        assert len(results) >= 1
        # The fallback entry has the npm-style name (without the npm: prefix)
        assert "server-filesystem" in results[0]["name"]
        assert results[0]["description"] == "MCP server for filesystem"

    def test_search_stub_for_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Even for unusual queries, the fallback produces a consistent result."""
        import httpx

        def _raise(*args: object, **kwargs: object) -> httpx.Response:
            raise httpx.ConnectError("Simulated network error")

        monkeypatch.setattr(httpx, "get", _raise)

        results = mcp_search("something-odd")
        assert len(results) >= 1
        assert "something-odd" in results[0]["name"]

    def _make_mock_response(self, json_data: dict) -> object:
        """Create a mock httpx.Response with request set for raise_for_status."""
        import httpx

        request = httpx.Request(
            "GET",
            "https://registry.npmjs.org/-/v1/search",
        )
        return httpx.Response(200, json=json_data, request=request)

    def test_search_successful(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful HTTP response returns parsed npm results."""
        import httpx

        mock_response = self._make_mock_response(
            {
                "objects": [
                    {
                        "package": {
                            "name": "@modelcontextprotocol/server-filesystem",
                            "description": "MCP server for filesystem operations",
                            "version": "1.0.0",
                        },
                    },
                    {
                        "package": {
                            "name": "@modelcontextprotocol/server-github",
                            "description": "MCP server for GitHub",
                            "version": "2.0.0",
                        },
                    },
                ]
            },
        )

        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response)

        results = mcp_search("filesystem")
        assert len(results) == 2
        assert results[0]["name"] == "@modelcontextprotocol/server-filesystem"
        assert results[0]["description"] == "MCP server for filesystem operations"
        assert results[0]["version"] == "1.0.0"
        assert results[1]["name"] == "@modelcontextprotocol/server-github"

    def test_search_empty_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty npm response returns empty list."""
        import httpx

        mock_response = self._make_mock_response({"objects": []})
        monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response)

        results = mcp_search("nonexistent")
        assert results == []


# ── mcp_install ────────────────────────────────────────────────────────


class TestMcpInstall:
    """Tests for mcp_install -- add MCP server to config."""

    def test_install_new(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Install a new MCP server creates a config entry."""
        _monkeypatch_config_path(monkeypatch, tmp_path)

        result = mcp_install("@modelcontextprotocol/server-filesystem")
        assert "Installed" in result
        assert "filesystem" in result

        configs = _load_configs()
        assert len(configs) == 1
        assert configs[0]["name"] == "filesystem"
        assert configs[0]["transport"] == "stdio"
        assert configs[0]["command"] == "npx"
        assert configs[0]["args"] == ["-y", "@modelcontextprotocol/server-filesystem"]

    def test_install_duplicate(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Installing a package with a duplicate name returns already-installed message."""
        _monkeypatch_config_path(monkeypatch, tmp_path)

        mcp_install("@modelcontextprotocol/server-filesystem")
        result = mcp_install("@modelcontextprotocol/server-filesystem")
        assert "already installed" in result

        configs = _load_configs()
        assert len(configs) == 1

    def test_install_simple_name(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Install a package without npm scope."""
        _monkeypatch_config_path(monkeypatch, tmp_path)

        result = mcp_install("server-git")
        assert "Installed" in result
        assert "git" in result

        configs = _load_configs()
        assert len(configs) == 1
        assert configs[0]["name"] == "git"
        assert configs[0]["args"] == ["-y", "server-git"]


# ── mcp_remove ─────────────────────────────────────────────────────────


class TestMcpRemove:
    """Tests for mcp_remove -- remove MCP server from config."""

    def test_remove_existing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Remove an existing server removes it from config."""
        _monkeypatch_config_path(monkeypatch, tmp_path)
        _save_configs([
            {"name": "filesystem", "transport": "stdio", "command": "npx",
             "args": ["-y", "@scope/server-fs"]},
            {"name": "search", "transport": "stdio", "command": "npx",
             "args": ["-y", "@scope/server-search"]},
        ])

        result = mcp_remove("search")
        assert "Removed" in result

        configs = _load_configs()
        assert len(configs) == 1
        assert configs[0]["name"] == "filesystem"

    def test_remove_nonexistent(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Remove a non-existent server returns not-found message."""
        _monkeypatch_config_path(monkeypatch, tmp_path)

        result = mcp_remove("nonexistent")
        assert "not found" in result

    def test_remove_last(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Remove the last server in config."""
        _monkeypatch_config_path(monkeypatch, tmp_path)
        _save_configs([
            {"name": "only-one", "transport": "stdio", "command": "npx",
             "args": ["-y", "server-only"]},
        ])

        result = mcp_remove("only-one")
        assert "Removed" in result
        assert _load_configs() == []
