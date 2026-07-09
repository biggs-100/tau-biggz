# Tau SDK

Tau can be used as a Python SDK for building custom agent workflows, IDEs,
bots, or automation tools. The public API is exported from ``tau_coding``.

## Quick Start

```python
import asyncio
from pathlib import Path
from tau_coding import (
    AgentHarness, AgentHarnessConfig,
    CodingSession, CodingSessionConfig,
    create_coding_tools, create_model_provider,
    load_provider_settings, resolve_provider_selection,
    SessionManager, jsonl_session_storage,
    build_system_prompt, BuildSystemPromptOptions,
)

async def main():
    # 1. Configure
    settings = load_provider_settings()
    selection = resolve_provider_selection(settings, provider_name="opencode-go")
    provider = create_model_provider(selection.provider, model=selection.model)
    tools = create_coding_tools(cwd=Path.cwd())
    system = build_system_prompt(BuildSystemPromptOptions(cwd=Path.cwd(), tools=tools))

    # 2. Create session
    harness = AgentHarness(AgentHarnessConfig(provider=provider, model=selection.model, system=system, tools=tools))
    manager = SessionManager()
    record = manager.prepare_session(cwd=Path.cwd(), model=selection.model, provider_name=selection.provider.name)
    session = await CodingSession.load(CodingSessionConfig(
        provider=harness.config.provider, model=record.model, cwd=record.cwd,
        storage=jsonl_session_storage(record.path), session_id=record.id,
        session_manager=manager, provider_name=selection.provider.name,
        provider_settings=settings, runtime_provider_config=selection.provider,
    ))

    # 3. Run
    async for event in session.prompt("Say hello"):
        if hasattr(event, "delta") and event.delta:
            print(event.delta, end="", flush=True)

    await session.aclose()

asyncio.run(main())
```

See ``examples/sdk/hello_tau.py`` for a runnable version.

## Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| ``AgentHarness`` | ``tau_agent.harness`` | Core agent loop (provider + tools + system) |
| ``AgentHarnessConfig`` | ``tau_agent.harness`` | Configuration for AgentHarness |
| ``CodingSession`` | ``tau_coding.session`` | High-level coding session wrapper |
| ``CodingSessionConfig`` | ``tau_coding.session`` | Session configuration |
| ``SessionManager`` | ``tau_coding.session_manager`` | CRUD for session records |
| ``ExtensionRegistry`` | ``tau_coding.extensions`` | Load and manage extensions |
| ``ProviderSettings`` | ``tau_coding.provider_config`` | Provider configuration + preferences |

## Key Functions

| Function | Returns | Purpose |
|----------|---------|---------|
| ``load_provider_settings()`` | ``ProviderSettings`` | Load providers.json + built-in catalog |
| ``resolve_provider_selection(settings, ...)`` | ``ProviderSelection`` | Pick a provider/model from settings |
| ``create_model_provider(config, model=...)`` | ``ClosableModelProvider`` | Create a runtime provider instance |
| ``create_coding_tools(cwd=...)`` | ``list[AgentTool]`` | Create built-in tools (read, write, edit, bash) |
| ``build_system_prompt(options)`` | ``str`` | Build the system prompt from tools + skills + context |
| ``create_extension_registry()`` | ``ExtensionRegistry`` | Discover and load extensions |
| ``jsonl_session_storage(path)`` | ``SessionStorage`` | JSONL-based session persistence |
| ``sync_models(settings)`` | ``(SyncResult, ProviderSettings)`` | Sync model metadata from models.dev |

## Architecture

```
                 ┌──────────────────────┐
                 │    Your Application   │
                 └──────────┬───────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │           CodingSession               │
        │  (prompt, tools, sessions, events)     │
        └───────────────────┬───────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │            AgentHarness                │
        │  (provider + loop + messages)          │
        └──────┬────────────────────┬───────────┘
               │                    │
        ┌──────┴──────┐    ┌───────┴────────┐
        │  Provider   │    │  Tools + System │
        │ (tau_ai)    │    │  (tau_coding)   │
        └─────────────┘    └────────────────┘
```

## RPC Mode

For non-Python integrations, use ``tau --rpc`` which exposes a JSONL protocol
over stdin/stdout. See ``src/tau_coding/rpc.py`` for the protocol details.

## Package Management

Install community extensions, skills, prompts, and themes:

```bash
tau package install git:github.com/user/repo
tau package list
tau package remove <name>
```
