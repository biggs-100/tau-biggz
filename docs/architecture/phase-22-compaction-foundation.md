# Phase 22: Compaction Replay Foundation

This phase starts Tau's compaction and context-management work without adding
model-driven summarization yet.

The implementation lives in:

```text
src/tau_agent/session/entries.py
src/tau_agent/session/memory.py
src/tau_coding/context_window.py
src/tau_coding/session.py
src/tau_coding/commands.py
```

## What was added

`CompactionEntry` is now meaningful during session replay.

When `SessionState.from_entries()` sees a compaction entry, it:

1. removes message entries whose ids appear in `replaces_entry_ids`
2. appends one provider-neutral summary message
3. keeps the original append-only entries intact

The summary message currently uses this stable form:

```text
Previous conversation summary:
<summary>
```

## Why It Exists

Tau needs compaction to reduce the active provider context while preserving the
full session file. This keeps Pi's append-only session property:

```text
session file = durable history
SessionState.messages = reconstructed active context
```

Manual `/compact` work can append `CompactionEntry` values without editing or
deleting old entries.

## Context Size Estimation

Tau now has deterministic approximate context-size helpers in `tau_coding`:

```python
estimate_text_tokens(...)
estimate_message_tokens(...)
estimate_tool_tokens(...)
estimate_context_tokens(...)
```

These helpers intentionally use a rough character-based estimate instead of a
provider-specific tokenizer. `/status` surfaces the current estimate as:

```text
Estimated context tokens: <count>
```

This gives future automatic compaction thresholds a stable application-layer
primitive without adding tokenizer policy to `tau_agent`.

## Manual Compaction

Tau now supports explicit-summary manual compaction in the TUI:

```text
/compact <summary>
```

The command appends a `CompactionEntry`, appends a new leaf pointer, replays the
session to rebuild active context, and replaces the in-memory harness transcript
for future turns.

The command deliberately requires a user-provided summary. Model-generated
summaries and automatic compaction thresholds are separate future steps.

## Boundary

This foundation is in `tau_agent` because replaying session entries is a
portable harness concern. It does not know about slash commands, Textual, Rich,
Tau home paths, token thresholds, or which model creates a summary.

Token estimation and command UX live in `tau_coding`. Automatic thresholds and
model-generated summaries belong in later `tau_coding` work.

## Tests

The phase is covered by:

```text
tests/test_session.py
tests/test_context_window.py
tests/test_commands.py
tests/test_coding_session.py
tests/test_tui_app.py
```

The tests verify:

- compaction entries round-trip through JSONL
- linear replay replaces compacted messages with a summary
- branch replay applies compaction only on the active branch path
- context-size estimation is deterministic
- `/status` includes an estimated context token count
- `/compact <summary>` requests compaction
- manual compaction persists entries and rebuilds future-turn context
