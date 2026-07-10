"""Shared fixtures for integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest

from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest

from tau_agent.session import JsonlSessionStorage, SessionStorage
from tau_agent.tools import AgentTool
from tau_ai import FakeProvider
from tau_ai.events import ProviderEvent
from tau_coding.session import CodingSession, CodingSessionConfig
from tau_coding.tools import create_coding_tools


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def fake_provider() -> FakeProvider:
    """A FakeProvider with no pre-configured streams."""
    return FakeProvider([])


@pytest.fixture
def session_storage(tmp_path: Path) -> JsonlSessionStorage:
    """JsonlSessionStorage pointing at tmp_path/session.jsonl."""
    return JsonlSessionStorage(tmp_path / "session.jsonl")


@pytest.fixture
def tools(tmp_path: Path) -> list[AgentTool]:
    """Real coding tools operating against tmp_path."""
    return create_coding_tools(cwd=tmp_path)


@pytest.fixture
def coding_session_factory(
    tools: list[AgentTool],
    tmp_path: Path,
    session_storage: JsonlSessionStorage,
) -> Callable[..., AsyncIterator[CodingSession]]:
    """Factory fixture: call with (streams, ...) to create a CodingSession."""

    async def _factory(
        streams: list[list[ProviderEvent]],
        *,
        provider: FakeProvider | None = None,
        storage: SessionStorage | None = None,
    ) -> CodingSession:
        prov = provider or FakeProvider(streams)
        session = await CodingSession.load(
            CodingSessionConfig(
                provider=prov,
                model="fake",
                cwd=tmp_path,
                storage=storage or session_storage,
                tools=tools,
                provider_name="openai",
                system="You are a helpful assistant. Use the available tools.",
            )
        )
        return session

    return _factory
