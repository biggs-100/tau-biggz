"""Minimal example of using Tau as an SDK.

Run with::

    uv run python examples/sdk/hello_tau.py
"""

import asyncio
from pathlib import Path

from tau_coding import (
    AgentHarness,
    AgentHarnessConfig,
    CodingSession,
    CodingSessionConfig,
    create_coding_tools,
    create_extension_registry,
    create_model_provider,
    load_provider_settings,
    resolve_provider_selection,
    SessionManager,
    build_system_prompt,
    BuildSystemPromptOptions,
    jsonl_session_storage,
)


async def main() -> None:
    # 1. Load provider settings (providers.json + catalog)
    provider_settings = load_provider_settings()

    # 2. Pick a provider and model
    selection = resolve_provider_selection(
        provider_settings,
        provider_name="opencode-go",
        model="deepseek-v4-flash",
    )

    # 3. Create a runtime provider
    provider = create_model_provider(
        selection.provider,
        model=selection.model,
    )

    # 4. Create coding tools (read, write, edit, bash, web_search, subagent_run)
    tools = create_coding_tools(
        cwd=Path.cwd(),
        extension_tools=create_extension_registry().get_tools(),
    )

    # 5. Build system prompt
    system = build_system_prompt(
        BuildSystemPromptOptions(
            cwd=Path.cwd(),
            tools=tools,
        )
    )

    # 6. Create a session manager and session record
    manager = SessionManager()
    record = manager.prepare_session(
        cwd=Path.cwd(),
        model=selection.model,
        provider_name=selection.provider.name,
    )

    # 7. Create the harness
    harness = AgentHarness(
        AgentHarnessConfig(
            provider=provider,
            model=selection.model,
            system=system,
            tools=tools,
        )
    )

    # 8. Load the coding session
    session = await CodingSession.load(
        CodingSessionConfig(
            provider=harness.config.provider,
            model=record.model,
            cwd=record.cwd,
            storage=jsonl_session_storage(record.path),
            session_id=record.id,
            session_manager=manager,
            provider_name=selection.provider.name,
            provider_settings=provider_settings,
            runtime_provider_config=selection.provider,
        )
    )

    # 9. Run a prompt and stream events
    print("Prompting Tau...")
    async for event in session.prompt("Say hello in one sentence."):
        # Events include MessageDeltaEvent, ToolExecutionStartEvent, etc.
        event_type = type(event).__name__
        if hasattr(event, "delta") and event.delta:
            print(event.delta, end="", flush=True)
        elif event_type == "AgentEndEvent":
            print()

    # 10. Cleanup
    await session.aclose()


if __name__ == "__main__":
    asyncio.run(main())
