# Design: Google Gemini Provider Hardening

## Technical Approach

Five independent changes to `src/tau_ai/google.py` and two data-model files, each following the existing patterns: Pydantic `BaseModel` with `extra="forbid"`, `httpx.MockTransport` for tests, and module-level helper functions. The thought-signature and thinking-text fields are added as optional/defaulted so no other provider is affected.

## Architecture Decisions

| Decision | Options | Choice & Rationale |
|----------|---------|--------------------|
| **thought_signature on ToolCall** | On ToolCall vs. separate dict vs. provider-only field | **On ToolCall**. REQ-SIG-8 mandates it. Since ToolCall is a Pydantic `BaseModel` with `extra="forbid"`, add a typed field; other providers see `None` by default (REQ-SIG-5). No serializer changes — `model_dump()` includes it automatically. |
| **thinking_text on AssistantMessage** | `str` vs `str \| None` vs skip/note | **`str = ""`** per REQ-THOUGHT-3. Empty string means no thinking. Avoids null checks in consumers. |
| **Schema sanitization** | Strip in `_tool_to_google` vs. separate function | **Separate `_sanitize_google_schema()`**. REQ-SAN-1 demands it. Pure function, no side effects, trivially testable. Called from `_tool_to_google` before building the parameters dict. |
| **xhigh normalization** | Duplicated in `_google_budget` and `_google_level` vs. shared helper | **Shared `_normalize_effort()`**. Centralizes the `"xhigh" → "high"` fold (REQ-XHIGH-8). Both budget and level helpers call it. |
| **Mocking in tests** | `httpx.MockTransport` per test vs. shared fixture | **Per-test `MockTransport`**. Matches the existing pattern in `test_tau_ai.py`. Each test is self-contained; no fixture complexity for SSE payload variances. A shared `_collect` helper reused. |

## Data Flow

```
UserMessage/AssistantMessage/ToolResultMessage
         │
         ▼
  _message_to_google()  ────  thoughtSignature echoed from ToolCall.thought_signature
  _tool_to_google()     ────  calls _sanitize_google_schema() on input_schema
  _google_thinking_config() ── uses _normalize_effort() for xhigh folding
         │
         ▼
  HTTP POST → SSE stream
         │
         ▼
  _parse_sse_line() → _loads_object() → _GoogleStreamParser.feed()
                                          │
                                          ├─ "text" + thought:true → ProviderThinkingDeltaEvent
                                          ├─ "text" + no thought  → ProviderTextDeltaEvent
                                          └─ "functionCall"       → ToolCall(thought_signature=...)
                                                                     → ProviderToolCallEvent
         │
         ▼
  _GoogleStreamParser.finalize()
     → AssistantMessage(content, tool_calls (with thought_signature), thinking_text)
     → ProviderResponseEndEvent
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/tau_agent/tools.py` | Modify | Add `thought_signature: str \| None = None` to `ToolCall` |
| `src/tau_agent/messages.py` | Modify | Add `thinking_text: str = ""` to `AssistantMessage` |
| `src/tau_ai/google.py` | Modify | Add `_sanitize_google_schema()`, `_normalize_effort()`, parser thought-signature extraction, thinking-text accumulation, sanitize in `_tool_to_google` |
| `tests/test_google_provider.py` | Create | ~20 test functions across 5 groups using `httpx.MockTransport` |

## Interfaces / Contracts

### ToolCall (add 1 field)

```python
class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    arguments: dict[str, JSONValue] = Field(default_factory=dict)
    thought_signature: str | None = None          # NEW — REQ-SIG-1
```

### AssistantMessage (add 1 field)

```python
class AssistantMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["assistant"] = "assistant"
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    thinking_text: str = ""                       # NEW — REQ-THOUGHT-1
```

### New helper signatures (in `src/tau_ai/google.py`)

```python
def _sanitize_google_schema(schema: dict[str, JSONValue]) -> dict[str, JSONValue]:
    """Recursively strip additionalProperties, $schema, default, title."""

def _normalize_effort(effort: str) -> str:
    """Fold xhigh → high; otherwise return effort unchanged."""
```

### Parser changes

- `_GoogleStreamParser.__init__`: add `self._thinking_text: list[str] = []`
- `_GoogleStreamParser.feed()`: on `functionCall` with `thoughtSignature` key, extract it: `tool_call_kwargs["thought_signature"] = function_call.get("thoughtSignature")`
- `_GoogleStreamParser.finalize()`: pass `thinking_text="".join(self._thinking_text)` to `AssistantMessage`

### Payload changes

- `_tool_to_google`: wrap `dict(tool.input_schema)` → `dict(_sanitize_google_schema(dict(tool.input_schema)))`
- `_message_to_google`: when building `functionCall` part, conditionally add `"thoughtSignature"` if `tool_call.thought_signature is not None`

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit (models) | `ToolCall.thought_signature` default and serialization | Direct assert on Pydantic model |
| Unit (models) | `AssistantMessage.thinking_text` default and serialization | Direct assert on Pydantic model |
| Unit (sanitize) | `_sanitize_google_schema` with all banned keys, nested, empty, clean schemas | Pure function tests, no mocking |
| Unit (xhigh) | `_normalize_effort` with xhigh, high, unknown values | Pure function tests |
| Integration (parser) | SSE line parsing, thinking parts, tool calls, thoughtSignature extraction | Feed raw SSE strings to `_GoogleStreamParser.feed()` + `finalize()` directly |
| Integration (stream) | Full HTTP responses via `MockTransport` — thinking, text, tool calls, mixed, errors, retries, cancellation, finish-reason mapping | `httpx.MockTransport` handler per scenario, `_collect()` helper, assert full event list |

**Test groups** in `tests/test_google_provider.py`:
1. **Model/field tests** (4–5 tests): ToolCall thought_signature, AssistantMessage thinking_text, serialization round-trip
2. **Sanitization tests** (6–7 tests): REQ-SAN-2 through SAN-12, including edge cases from spec
3. **Thinking-level tests** (4–5 tests): REQ-XHIGH-1 through XHIGH-8, payload assertions via MockTransport
4. **SSE streaming tests** (8–10 tests): REQ-TEST-3 through TEST-9, TEST-18, TEST-22, TEST-23, covering thinking, text, tool calls, mixed streams, finish reasons
5. **Error/retry tests** (5–6 tests): REQ-TEST-10 through TEST-14, TEST-24, covering HTTP errors, retries, network errors, cancellation

**Coverage target**: `>= 85%` line coverage for `src/tau_ai/google.py` (REQ-TEST-2). Measured via `uv run pytest --cov=tau_ai.google tests/test_google_provider.py`.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.

## Migration / Rollout

No migration required. All new fields have defaults (`None`/`""`), so existing sessions loaded from JSONL will deserialize without error (Pydantic fills missing fields from defaults). New sessions will have the new fields populated on write.

## Implementation Order

1. **ToolCall.thought_signature** (src/tau_agent/tools.py) — one-line field add, no behavior change. Safest first step.
2. **AssistantMessage.thinking_text** (src/tau_agent/messages.py) — one-line field add.
3. **Schema sanitization** (src/tau_ai/google.py) — add `_sanitize_google_schema()` + `_normalize_effort()` pure functions, wire into `_tool_to_google`. Fully testable without HTTP.
4. **Parser changes** (src/tau_ai/google.py) — thought-signature extraction, thinking-text accumulation, `finalize()` wiring.
5. **Payload changes** (src/tau_ai/google.py) — thought-signature echo in `_message_to_google`.
6. **Tests** (tests/test_google_provider.py) — all groups, last because it depends on all the changes above.

Steps 1–5 can be implemented sequentially without conflict. Each is independently revertible (per proposal rollback plan).

## Open Questions

- None — all decisions are resolved by spec requirements.
