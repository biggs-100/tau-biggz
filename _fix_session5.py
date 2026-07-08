"""Fix session.py - add subagent injection to harness_system_prompt."""
with open('src/tau_coding/session.py', 'rb') as f:
    raw = f.read()
content = raw.decode('utf-8')

BS = '\\'
NL = BS + 'n'

append_block = f"""
    append_text = config.append_system_prompt or ""
    if harness.subagents:
        append_text += "{NL}{NL}## Available sub-agents{NL}{NL}"
        append_text += "You can delegate tasks using subagent_run(task, instructions).{NL}{NL}"
        for sa in harness.subagents:
            append_text += f"- " + sa.name + ": " + sa.instructions + "{NL}"
    return build_system_prompt(BuildSystemPromptOptions(
"""

old = "    if harness.name != \"coding\" and harness.personality.system_prompt:\n        custom_prompt = harness.personality.system_prompt\n    return build_system_prompt("
new = "    if harness.name != \"coding\" and harness.personality.system_prompt:\n        custom_prompt = harness.personality.system_prompt" + append_block

if old not in content:
    print('OLD NOT FOUND')
    exit(1)

content = content.replace(old, new)

# Fix the closing args
content = content.replace(
    'append_system_prompt=config.append_system_prompt,\n            context_files=resources.context_files,\n        )\n    )',
    'append_system_prompt=append_text,\n            context_files=resources.context_files,\n        )\n    )'
)

with open('src/tau_coding/session.py', 'wb') as f:
    f.write(content.encode('utf-8'))

import py_compile
py_compile.compile('src/tau_coding/session.py', doraise=True)
print('OK')
