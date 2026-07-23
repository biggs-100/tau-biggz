# Tasks: Google Gemini Provider Hardening

## Task List

| ID | Title | Description | Files | Dependencies | Est. Lines | Status |
|----|-------|-------------|-------|-------------|------------|--------|
| T1 | Add `thought_signature` to `ToolCall` | Add `thought_signature: str \| None = None` field to the Pydantic `ToolCall` model. One-line field add with default `None` — zero behavioral impact on other providers. | `src/tau_agent/tools.py` | None | 2 | ✅ |
| T2 | Add `thinking_text` to `AssistantMessage` | Add `thinking_text: str = ""` field to the Pydantic `AssistantMessage` model. Empty string default avoids null checks in consumers. | `src/tau_agent/messages.py` | None | 2 | ✅ |
| T3 | Add `_sanitize_google_schema()` and `_normalize_effort()` | Two pure helper functions. `_sanitize_google_schema()` recursively strips `additionalProperties`, `$schema`, `default`, `title` from JSON Schema dicts. `_normalize_effort()` folds `"xhigh"` to `"high"`, replacing duplicated logic in `_google_budget` and `_google_level`. | `src/tau_ai/google.py` | None | 30 | ✅ |
| T4 | Wire sanitization into `_tool_to_google()` | Call `_sanitize_google_schema()` in `_tool_to_google()` so tool input schemas are sanitized before being sent to the Gemini API. Changes one expression. | `src/tau_ai/google.py` | T3 | 3 | ✅ |
| T5 | Parser — thoughtSignature extraction and thinking-text accumulation | In `_GoogleStreamParser`: extract `functionCall.thoughtSignature` during `feed()` and store on `ToolCall.thought_signature`; accumulate thinking parts into `thinking_text` on the final `AssistantMessage` in `finalize()`. | `src/tau_ai/google.py` | T1, T2 | 8 | ✅ |
| T6 | Payload — echo thoughtSignature in `_message_to_google()` | When building `functionCall` parts for `AssistantMessage` tool calls, conditionally include `"thoughtSignature"` field if `tool_call.thought_signature is not None`. | `src/tau_ai/google.py` | T1 | 5 | ✅ |
| T7 | Create `tests/test_google_provider.py` | Comprehensive test file with 63 tests across 7 groups: model/field tests, sanitization tests, thinking-level tests, SSE streaming tests, error/retry tests, message conversion tests, parser edge case tests. Uses `httpx.MockTransport` per-test pattern. Shared `_collect` helper used inline. Coverage: 98% of `tau_ai.google`. | `tests/test_google_provider.py` | T1, T2, T3, T4, T5, T6 | 420 | ✅ |

**Totals**: 7 tasks, 4 files, ~470 estimated changed lines (+ ~420 test file = ~470 total production + test additions).

## Implementation Order

### Wave 1 — Data model and pure helpers (parallel, no dependencies)

```
T1 ─── ToolCall.thought_signature
T2 ─── AssistantMessage.thinking_text
T3 ─── _sanitize_google_schema() + _normalize_effort()
```

These three are fully independent. T1 and T2 are one-line field adds on Pydantic models in separate files. T3 adds pure functions in `google.py` that are not yet wired into anything.

### Wave 2 — Wire into google.py (parallel after dependencies resolved)

```
T4 ─── Wire sanitization into _tool_to_google()     ← needs T3
T5 ─── Parser: thoughtSignature + thinking_text     ← needs T1, T2
T6 ─── Payload: echo thoughtSignature               ← needs T1
```

T4, T5, T6 modify distinct areas of `google.py` (tool serialization, parser, message builder) and can be implemented in any order once their dependencies are met. No merge conflicts expected.

### Wave 3 — Tests (depends on all production code)

```
T7 ─── tests/test_google_provider.py                ← needs T1–T6
```

Last because it exercises all changes. If implemented earlier, tests would fail on imports of `thought_signature` / `thinking_text`.

## Detailed Task Breakdown

### T1: Add `thought_signature` to `ToolCall`

**What**: Add one field to the `ToolCall` Pydantic model.

```python
class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    arguments: dict[str, JSONValue] = Field(default_factory=dict)
    thought_signature: str | None = None          # ← ADD
```

**File**: `src/tau_agent/tools.py`
**Est. lines**: +2 (field definition + type import if needed — no import needed for built-in types)
**Verification**: `ToolCall(thought_signature="abc")` constructs; `ToolCall()` defaults to `None`; `model_dump()` includes it.

### T2: Add `thinking_text` to `AssistantMessage`

**What**: Add one field to the `AssistantMessage` Pydantic model.

```python
class AssistantMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["assistant"] = "assistant"
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    thinking_text: str = ""                       # ← ADD
```

**File**: `src/tau_agent/messages.py`
**Est. lines**: +2
**Verification**: `AssistantMessage()` defaults `thinking_text` to `""`; `AssistantMessage(thinking_text="reasoned")` carries the value; `model_dump()` includes it.

### T3: Add `_sanitize_google_schema()` and `_normalize_effort()`

**What**:
- `_sanitize_google_schema(schema: dict[str, JSONValue]) -> dict[str, JSONValue]`: Recursively deep-copies the schema dict and removes banned keys (`additionalProperties`, `$schema`, `default`, `title`) from every nesting level. Handles `properties`, `items`, `allOf`, `anyOf`, `oneOf`, `not`, and non-dict edge cases.
- `_normalize_effort(effort: str) -> str`: One-liner that folds `"xhigh"` → `"high"`, passes everything else through. Centralizes the duplicated logic currently in `_google_budget` and `_google_level`.

**Refactoring required**:
- `_google_budget()`: Remove `normalized = effort.lower()` / `if normalized == "xhigh": normalized = "high"` block; replace with `normalized = _normalize_effort(effort.lower())`
- `_google_level()`: Same replacement.
- Both functions currently call `effort.lower()` + `normalized == "xhigh"` check. The new pattern: `normalized = _normalize_effort(effort.lower())` — shorter and centralized.

**File**: `src/tau_ai/google.py`
**Est. lines**: ~30 (sanitize: ~22, normalize: ~3, refactoring both callers: ~5)
**Edge cases in sanitize**: `None` values for nested containers, empty dict `{}`, array schemas with `items`, schemas with no banned keys (pass-through).

### T4: Wire sanitization into `_tool_to_google()`

**What**: Change `_tool_to_google()` to sanitize the input schema before building the parameters dict.

```python
def _tool_to_google(tool: AgentTool) -> dict[str, JSONValue]:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": dict(_sanitize_google_schema(dict(tool.input_schema))),
    }
```

**File**: `src/tau_ai/google.py`
**Est. lines**: ~3 (edit one expression, add import if needed — but function is in same module)

### T5: Parser — thoughtSignature extraction and thinking-text accumulation

**What**:
1. In `_GoogleStreamParser.__init__`: The `_thinking_parts` list already exists. No new field needed — but `thinking_text` content is currently accumulated but not passed to `AssistantMessage`.
2. In `_GoogleStreamParser.feed()`: When building the `ToolCall` from a `functionCall` part, extract `thoughtSignature`:
   ```python
   thought_signature = function_call.get("thoughtSignature")  # str | None
   tool_call = ToolCall(
       id=...,
       name=...,
       arguments=...,
       thought_signature=thought_signature,  # ← ADD
   )
   ```
3. In `_GoogleStreamParser.finalize()`: Pass `thinking_text` to `AssistantMessage`:
   ```python
   AssistantMessage(
       content="".join(self._content_parts),
       tool_calls=self._tool_calls,
       thinking_text="".join(self._thinking_parts),  # ← ADD
   )
   ```

**File**: `src/tau_ai/google.py`
**Est. lines**: ~8
**Note**: `_thinking_parts` list already exists and is populated in `feed()` for thinking parts. The only real additions are the `thought_signature` extraction and the `thinking_text=` kwarg in `finalize()`.

### T6: Payload — echo thoughtSignature in `_message_to_google()`

**What**: In `_message_to_google()`, when building the `functionCall` dict for each `ToolCall` in an `AssistantMessage`, conditionally include `thoughtSignature`:

```python
for tool_call in message.tool_calls:
    fc: dict[str, JSONValue] = {
        "id": tool_call.id,
        "name": tool_call.name,
        "args": dict(tool_call.arguments),
    }
    if tool_call.thought_signature is not None:
        fc["thoughtSignature"] = tool_call.thought_signature
    parts.append({"functionCall": fc})
```

**File**: `src/tau_ai/google.py`
**Est. lines**: ~5 (expand inline dict to built dict)

### T7: Create `tests/test_google_provider.py`

**What**: New test file with ~25 tests covering all spec requirements:

| Group | Tests | Coverage | Approach |
|-------|-------|----------|----------|
| **Model/field tests** | 4–5 tests | REQ-SIG-1, REQ-SIG-5, REQ-THOUGHT-1–3 | Direct asserts on `ToolCall` and `AssistantMessage` Pydantic models |
| **Sanitization tests** | 6–7 tests | REQ-SAN-2 through SAN-12 | Pure function calls to `_sanitize_google_schema()` |
| **Thinking-level tests** | 4–5 tests | REQ-XHIGH-1 through XHIGH-8 | Payload assertions via `httpx.MockTransport` |
| **SSE streaming tests** | 8–10 tests | REQ-TEST-3 through TEST-9, 18, 22, 23 | Feed raw SSE to `MockTransport`, assert full event list |
| **Error/retry tests** | 5–6 tests | REQ-TEST-10 through TEST-14, 24 | HTTP error responses with `MockTransport` |

**Conventions**:
- Use same `httpx.MockTransport` per-test pattern as `test_tau_ai.py`
- Reuse the `_collect` helper (or a shared import from test_tau_ai)
- Use `pytest.mark.anyio` for async tests
- All tests use fake HTTP — no real network calls
- Coverage target: >= 85% line coverage for `src/tau_ai/google.py`

**File**: `tests/test_google_provider.py`
**Est. lines**: ~420

## Dependency Graph

```
                  ┌────────────────┐
                  │  No deps       │
                  │                │
     ┌────────────┼─── T1 ─────────┼─── tool.py (2 lines)
     │            │                │
     │            │   T2           │─── messages.py (2 lines)
     │            │                │
     │            │   T3           │─── google.py (30 lines)
     │            └────────────────┘
     │                    │
     │                    ▼
     │            ┌────────────────┐
     │            │  Wave 2        │
     │            │                │
     ├────────────┼─── T4 ─────────┼─── google.py (needs T3)
     │            │                │
     │            │   T5           │─── google.py (needs T1, T2)
     │            │                │
     │            │   T6           │─── google.py (needs T1)
     │            └────────────────┘
     │                    │
     │                    ▼
     │            ┌────────────────┐
     │            │  Wave 3        │
     │            │                │
     └────────────┼─── T7 ─────────┼─── test_google_provider.py
                  │                │      (needs T1-T6)
                  └────────────────┘
```

## Sequencing Notes

- **T1 + T2 + T3 can be done in parallel** — zero overlap between files or functions.
- **T4 + T5 + T6 touch the same file** (`google.py`) but distinct functions (`_tool_to_google`, `_GoogleStreamParser.feed/finalize`, `_message_to_google`). No merge conflicts expected, but implement in one contiguous pass to minimize context switching.
- **T7 must be last** because it imports and exercises all new code paths.

## Review Workload Forecast

| Metric | Value |
|--------|-------|
| **Estimated changed lines** | ~470 (production) + ~420 (test) = **~470 net new** (tests are changes to repo but new file) |
| **Files modified** | 3 (`tools.py`, `messages.py`, `google.py`) |
| **Files created** | 1 (`tests/test_google_provider.py`) |
| **Chained PRs recommended** | **Yes** — subject to user decision after reviewing forecast |
| **Decision needed before apply** | User to decide: single PR (~470 lines) or chained PRs (data model → google.py → tests) |

### Chained PR proposal

If chained, split into 3 PRs:

1. **PR-A**: T1 + T2 (data model fields) — ~4 lines, trivial review, unblocks parallel work
2. **PR-B**: T3 + T4 + T5 + T6 (all google.py changes) — ~46 lines, single-file logical changes
3. **PR-C**: T7 (test file) — ~420 lines, standalone new file

This keeps each reviewed unit under 100 lines until the test file, which is inherently large but mechanically straightforward (no behavioral logic — just proves existing code works).

### Risks

| Risk | Likelihood | Impact | Notes |
|------|------------|--------|-------|
| Merge conflict in `google.py` if other changes land during implementation | Low | Medium | T4/T5/T6 are in clearly separated functions — unlikely |
| Test file size (420 lines) makes review dense | High | Low | Tests are repetitive and pattern-based; can spot-check |
| `_normalize_effort` refactoring changes 2 callers | Low | Low | Pure replace: same input → same output |
| Missing test coverage edge case discovered late | Low | Medium | Coverage gate (85%) catches this before merge |
