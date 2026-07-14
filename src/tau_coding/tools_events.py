"""Tool-event wrapping and extension-tool conversion for Tau coding tools.

Extracted from tools.py to reduce module size.
"""

from __future__ import annotations

from collections.abc import Mapping

from tau_agent.tools import AgentTool, AgentToolResult, ToolCancellationToken
from tau_agent.types import JSONValue
from tau_coding.extensions import ToolRegistration, get_default_registry
from tau_coding.harness import HarnessApproval
from tau_coding.tools_security import _check_tool_approval


def _wrap_tool_with_events(
    tool: AgentTool,
    approval: HarnessApproval | None = None,
) -> AgentTool:
    """Wrap a tool's executor to fire extension events before/after execution."""
    original_executor = tool.executor

    async def event_dispatched_executor(
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        # 1. Approval chain check
        denial = _check_tool_approval(tool.name, approval, arguments=dict(arguments))
        if denial is not None:
            return AgentToolResult(
                tool_call_id="ext",
                name=tool.name,
                ok=False,
                content=denial,
                error=denial,
            )

        # 2. Extension event dispatch
        registry = get_default_registry()
        event_data = {
            "tool_name": tool.name,
            "input": dict(arguments),
            "tool_call_id": "ext_event",
        }
        results = registry.dispatch_event("tool_call", event_data)
        for result in results:
            if isinstance(result, dict) and result.get("block"):
                reason = result.get("reason", "Blocked by extension")
                return AgentToolResult(
                    tool_call_id="ext",
                    name=tool.name,
                    ok=False,
                    content=reason,
                    error=reason,
                )

        # 3. Actual execution
        try:
            result = await original_executor(arguments, signal=signal)
        except Exception as exc:
            registry.dispatch_event(
                "after_tool_call",
                {
                    "tool_name": tool.name,
                    "input": dict(arguments),
                    "result": {"ok": False, "content": str(exc)},
                },
            )
            return AgentToolResult(
                tool_call_id="ext",
                name=tool.name,
                ok=False,
                content=str(exc),
                error=str(exc),
            )
        registry.dispatch_event(
            "after_tool_call",
            {
                "tool_name": tool.name,
                "input": dict(arguments),
                "result": {"ok": result.ok, "content": result.content},
            },
        )
        return result

    return AgentTool(
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
        executor=event_dispatched_executor,
        prompt_snippet=tool.prompt_snippet,
        prompt_guidelines=tool.prompt_guidelines,
    )


def _extension_tool_to_agent_tool(ext_tool: ToolRegistration) -> AgentTool:
    """Convert an extension tool registration into an AgentTool."""
    properties: dict[str, JSONValue] = {}
    required: list[JSONValue] = []
    for param in ext_tool.parameters:
        properties[param["name"]] = {"type": "string", "description": f"Parameter {param['name']}"}
        required.append(param["name"])
    input_schema: dict[str, JSONValue] = {
        "type": "object",
        "properties": properties,
        "required": required,
    }

    async def executor(
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        try:
            result = ext_tool.executor(**dict(arguments))
            if hasattr(result, "__await__"):
                result = await result
            return AgentToolResult(
                tool_call_id="ext",
                name=ext_tool.name,
                ok=True,
                content=str(result),
            )
        except Exception as exc:
            return AgentToolResult(
                tool_call_id="ext",
                name=ext_tool.name,
                ok=False,
                content=str(exc),
                error=str(exc),
            )

    return AgentTool(
        name=ext_tool.name,
        description=ext_tool.description,
        input_schema=input_schema,
        executor=executor,
    )
