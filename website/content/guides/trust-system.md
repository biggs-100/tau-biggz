---
title: Trust system
description: Persist tool approval decisions so you're not asked every time — trust tools once and run them freely.
---

When a harness approval policy resolves to `"ask"` for a tool, Tau normally
blocks execution and prompts you for a decision. The **trust system** lets you
make that decision persistent: trust a tool once with `/trust add`, and it runs
without asking again.

## How it works

Trust decisions are stored in `~/.tau/trust.json`:

```json
{
  "version": 1,
  "trusted_tools": [
    "bash",
    "read",
    "write"
  ]
}
```

The trust store is checked **after** the harness approval chain and **after**
extension event handlers. If a tool resolves to `"ask"` at the approval level,
Tau checks the trust store. If the tool is trusted, it executes; otherwise the
user sees a denial message with guidance on how to trust it.

## The `/trust` command

Use `/trust` from the TUI prompt to manage trusted tools:

```text
/trust add <tool>      Trust a tool (persistent)
/trust remove <tool>   Remove trust for a tool
/trust list            Show all trusted tools
/trust help            Show usage
```

### Adding trust

```text
/trust add bash
```

After this, `bash` tool calls that resolve to `"ask"` will run automatically.
The trust decision is persisted to `~/.tau/trust.json` and survives restarts.

### Removing trust

```text
/trust remove bash
```

The tool is removed from the trusted set, and future `"ask"`-resolved calls
will prompt for approval again.

### Listing trusted tools

```text
/trust list
```

Shows every currently trusted tool name, one per line.

## Ask mode

When a tool's approval policy is `"ask"` and it has not been trusted, Tau shows
a structured denial message:

```text
Tool 'bash' requires your approval.
Args: command=rm -rf /tmp/cache.
Use /trust add bash to trust it.
```

The message includes the tool name, up to three argument key-value pairs
(values longer than 60 characters are truncated), and guidance for trusting the
tool.

## Approval chain order

The complete tool approval chain runs in this order:

1. **Harness approval policy** — check `[approval]` rules in the harness
   configuration (see [Harness]({{< relref "./harness.md" >}})).
2. **Extension event handlers** — `on("tool_call")` handlers registered by
   extensions can block the call (see [Extensions]({{< relref "./extensions.md" >}})).
3. **Trust store** — if the policy resolved to `"ask"`, check `trust.json`.
4. **Tool execution** — if nothing blocked, the tool runs.

If any step blocks the call, the remaining steps are skipped.

## See also

- [Harness system]({{< relref "./harness.md" >}}) — configuring approval policies
- [Extensions]({{< relref "./extensions.md" >}}) — event-driven tool blocking
- [Sandboxing]({{< relref "./sandboxing.md" >}}) — path-level access control
