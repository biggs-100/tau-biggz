"""Shared test configuration for tau-biggz tests."""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "anyio: run the test via anyio")
