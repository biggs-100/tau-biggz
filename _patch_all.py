"""Apply harness + MCP + subagent integration to session.py."""
import py_compile

with open('src/tau_coding/session.py', 'rb') as f:
    raw = f.read()
content = raw.decode('utf-8')

NL = '\\n'  # literal \n (two chars) for Python source

# 1. Add imports
content = content.replace(
    "from tau_coding.extensions import get_default_registry",
    "from tau_coding.extensions import get_default_registry\nfrom tau_coding.harness import HarnessDefinition, coding_harness"
)

# 2. Add harness field to CodingSessionConfig
content = content.replace(
    "    shell_command_prefix: str | None = None",
    "    shell_command_prefix: str | None = None\n    harness: HarnessDefinition | None = None"
)

# 3. Build helpers
helpers = f"""

def _harness_filtered_tools(config):
    from tau_coding.extensions import get_default_registry
    from tau_coding.harness import get_active_harness
    from tau_coding.tools import create_coding_tools
    all_tools = create_coding_tools(
        cwd=config.cwd,
        shell_command_prefix=config.shell_command_prefix,
        extension_tools=get_default_registry().get_tools(),
    )
    h = get_active_harness()
    if h.name == "coding":
        return all_tools
    allowed = set(h.tools.builtin)
    if not allowed:
        return all_tools
    return [t for t in all_tools if t.name in allowed]


def _harness_system_prompt(config, tools, resources):
    from tau_coding.harness import get_active_harness
    from tau_coding.system_prompt import BuildSystemPromptOptions, build_system_prompt
    h = get_active_harness()
    custom = config.custom_system_prompt
    if h.name != "coding" and h.personality.system_prompt:
        custom = h.personality.system_prompt
    append_text = config.append_system_prompt or ""
    if h.subagents:
        append_text += "{NL}{NL}## Available sub-agents{NL}{NL}"
        append_text += "You can delegate tasks using subagent_run(task, instructions).{NL}{NL}"
        for sa in h.subagents:
            append_text += f"- {{sa.name}}: {{sa.instructions}}{NL}"
    return build_system_prompt(
        BuildSystemPromptOptions(
            cwd=config.cwd,
            tools=tools,
            skills=resources.skills,
            custom_prompt=custom,
            append_system_prompt=append_text,
            context_files=resources.context_files,
        )
    )

"""

# Insert helpers before _initial_model_for_config
marker = "def _initial_model_for_config"
idx = content.find("\n" + marker)
content = content[:idx] + helpers + content[idx:]

# 4. Replace tools creation
content = content.replace(
    "            tools = (\n                config.tools\n                if config.tools is not None\n                else create_coding_tools(\n                    cwd=config.cwd,\n                    shell_command_prefix=config.shell_command_prefix,\n                    extension_tools=get_default_registry().get_tools(),\n                )\n            )",
    "            tools = (\n                config.tools\n                if config.tools is not None\n                else _harness_filtered_tools(config)\n            )"
)

# 5. Replace system prompt creation
content = content.replace(
    "            system = (\n                config.system\n                if config.system is not None\n                else build_system_prompt(\n                    BuildSystemPromptOptions(\n                        cwd=config.cwd,\n                        tools=tools,\n                        skills=resources.skills,\n                        custom_prompt=config.custom_system_prompt,\n                        append_system_prompt=config.append_system_prompt,\n                        context_files=resources.context_files,\n                    )\n                )\n            )",
    "            system = (\n                config.system\n                if config.system is not None\n                else _harness_system_prompt(config, tools, resources)\n            )"
)

# 6. Add MCP connection
content = content.replace(
    "            resource_paths = resource_paths_with_cwd(config.resource_paths, config.cwd)",
    "            _connect_mcp_servers(config.cwd)\n            resource_paths = resource_paths_with_cwd(config.resource_paths, config.cwd)"
)

# 7. Add MCP disconnect in aclose
content = content.replace(
    "    async def aclose(self) -> None:\n        \"\"\"Close runtime providers created by this coding session.\"\"\"",
    "    async def aclose(self) -> None:\n        \"\"\"Close runtime providers and MCP connections.\"\"\""
)
content = content.replace(
    "        self._owned_providers.clear()",
    "        self._owned_providers.clear()\n        await _disconnect_mcp_servers()"
)

# 8. Add MCP helper functions
mcp_helpers = f"""

def _connect_mcp_servers(cwd=None):
    from tau_coding.mcp_integration import get_mcp_registry, load_mcp_config
    reg = get_mcp_registry()
    if reg.connected:
        return
    configs = load_mcp_config(cwd)
    for cfg in configs:
        reg.add_server(cfg)
    import anyio
    connected = anyio.run(reg.connect_all)
    if connected:
        msg = f"  MCP connected: {{', '.join(connected)}}"
        __import__("sys").stderr.write(msg + "{NL}")


async def _disconnect_mcp_servers():
    from tau_coding.mcp_integration import get_mcp_registry
    reg = get_mcp_registry()
    if reg.connected:
        await reg.disconnect_all()

"""

marker2 = "def _unavailable_thinking_message"
idx2 = content.find("\n" + marker2)
content = content[:idx2] + mcp_helpers + content[idx2:]

with open('src/tau_coding/session.py', 'wb') as f:
    f.write(content.encode('utf-8'))

py_compile.compile('src/tau_coding/session.py', doraise=True)
print('OK')
