---
title: "Tau release notes"
description: "New features, fixes, and changes in each Tau release — including tau-biggz-specific additions."
layout: releases
build:
  list: false
---

Tau-biggz adds several features beyond the original Tau codebase:

- **Extension system** — `@tool`, `@command`, `@on`, and `@ui_widget` decorators
  for custom tools, slash commands, event handlers, and status-bar widgets.
- **Harness system** — `.tau/harness.toml` for configuring agent personalities,
  tool approval chains, and sandbox policies.
- **Trust system** — `/trust add|remove|list` commands and a persistent
  `trust.json` store for tool approval decisions.
- **MCP integration** — Model Context Protocol support with
  `tau mcp install/remove/list/search` commands.
- **Path sandboxing** — strict-mode path validation for file tools,
  configurable via `[sandbox]` harness settings.
- **`--unsafe` flag** — disable sandbox restrictions for a session.
- **Codebase refactoring** — tools module split into domain-specific files
  (`tools_security.py`, `tools_validation.py`, `tools_types.py`).
- **Mypy strict-mode compliance** — type annotations added across the
  codebase, with ~30 mypy fixes in core modules.
