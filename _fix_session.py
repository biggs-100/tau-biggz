"""Fix the broken _harness_system_prompt function."""
with open('src/tau_coding/session.py', 'rb') as f:
    raw = f.read()
content = raw.decode('utf-8')

start = content.find('def _harness_system_prompt')
end = content.find('\n\n\n', start + 200)
if start < 0 or end < 0:
    print('NOT FOUND')
    exit(1)

clean = """def _harness_system_prompt(config, tools, resources):
    \"\"\"Build system prompt using harness personality.\"\"\"
    from tau_coding.harness import get_active_harness
    from tau_coding.system_prompt import BuildSystemPromptOptions, build_system_prompt
    harness = get_active_harness()
    custom_prompt = config.custom_system_prompt
    if harness.name != "coding" and harness.personality.system_prompt:
        custom_prompt = harness.personality.system_prompt
    return build_system_prompt(
        BuildSystemPromptOptions(
            cwd=config.cwd,
            tools=tools,
            skills=resources.skills,
            custom_prompt=custom_prompt,
            append_system_prompt=config.append_system_prompt,
            context_files=resources.context_files,
        )
    )

"""

content = content[:start] + clean + content[end:]

with open('src/tau_coding/session.py', 'wb') as f:
    f.write(content.encode('utf-8'))
print('OK')

import py_compile
py_compile.compile('src/tau_coding/session.py', doraise=True)
print('Compiles OK')
