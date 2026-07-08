"""Fix session.py - add subagent injection to harness_system_prompt."""
with open('src/tau_coding/session.py', 'rb') as f:
    raw = f.read()
content = raw.decode('utf-8')

# Use chr() to build escape sequences to avoid Python parsing issues
BS = '\\'  # single backslash
NL = BS + 'n'  # \n as two characters in source

append_block = f'''
    append_text = config.append_system_prompt or ""
    if harness.subagents:
        append_text += "{NL}{NL}## Available sub-agents{NL}{NL}"
        append_text += "You can delegate tasks using subagent_run(task, instructions).{NL}{NL}"
        for sa in harness.subagents:
            append_text += f"- {{sa.name}}: {{sa.instructions}}{NL}"
            if sa.tools:
                append_text += f"  Tools: {{chr(39) + chr(44) + chr(32) + chr(39)}.join(sa.tools)}}{NL}"
'''

old = "    if harness.name != \"coding\" and harness.personality.system_prompt:\n        custom_prompt = harness.personality.system_prompt\n    return build_system_prompt("
new = "    if harness.name != \"coding\" and harness.personality.system_prompt:\n        custom_prompt = harness.personality.system_prompt" + append_block + "    return build_system_prompt("

if old not in content:
    print('OLD NOT FOUND')
    idx = content.find('custom_prompt = harness.personality.system_prompt')
    print(repr(content[idx:idx+100]))
    exit(1)

content = content.replace(old, new)
content = content.replace(
    'append_system_prompt=config.append_system_prompt,',
    'append_system_prompt=append_text,'
)

with open('src/tau_coding/session.py', 'wb') as f:
    f.write(content.encode('utf-8'))

import py_compile
py_compile.compile('src/tau_coding/session.py', doraise=True)
print('OK')
