# Proposal: Google Gemini Provider Hardening

## Intent

Google Gemini provider exists at `src/tau_ai/google.py` (~380 lines) with 1 test, no thoughtSignature round-trip (multi-turn tool calls silently fail), no schema sanitization (API rejects `additionalProperties`), and collapsed thinking levels. Hardening to production quality.

## Scope

### In Scope
- Tests: thinking streaming, tool call streaming, errors/retry, thinking levels, schema sanitization, message conversion (~400 lines)
- xhigh level: support for Gemini 3.x, lift fold-to-high with fallback (~20 lines)
- thoughtSignature: store on `ToolCall`, echo in subsequent `functionCall` (~80 lines)
- Schema sanitization: reimplement `_sanitize_google_schema()` — strip `additionalProperties`, `$schema`, `default`, `title` (~60 lines)
- Thought preservation: add `thinking_text` to `AssistantMessage` or document limitation (~40 lines)

### Out of Scope
Multimodal, new model families, response caching, message model refactor.

## Capabilities

No spec-level changes — pure hardening of existing behavior.

### New / Modified Capabilities

None.

## Approach

| Item | Approach |
|------|----------|
| Tests | 5 groups in `tests/test_google_provider.py` using existing fake-provider patterns |
| xhigh | Verify API support, lift fold, fallback to high with logged warning |
| thoughtSignature | `Optional[str]` on `ToolCall`; populate from `functionCall.thoughtSignature`; echo in next turn |
| Sanitization | Strip `additionalProperties`, `$schema`, `default`, `title` before API call |
| Thought | `thinking_text` field on `AssistantMessage` if feasible, else document |

## Affected Areas

| Area | Change |
|------|--------|
| `src/tau_ai/google.py` | Sanitization, thoughtSignature, thinking levels |
| `src/tau_agent/tool.py` | `thought_signature: str \| None` on `ToolCall` |
| `src/tau_agent/message.py` | `thinking_text` on `AssistantMessage` |
| `tests/test_google_provider.py` | Comprehensive test expansion |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| thoughtSignature affects other providers | Low | `Optional[str]`, only google sets it |
| API rejects new thinking levels | Medium | Fallback to high, log warning |
| Schema sanitization misses keywords | Low | Test against known JSON Schema keywords |
| Thought preservation needs model changes | Medium | Document limitation if blocked |

## Rollback Plan

Items are independently revertible. Full rollback: remove `thought_signature` from `ToolCall`, restore no-op sanitization, revert level logic.

## Dependencies

`google-genai` SDK (already a dependency).

## Success Criteria

- [ ] All streaming paths tested: thinking, tool calls, errors, retry, timeouts
- [ ] thoughtSignature round-trip verified in multi-turn test
- [ ] xhigh folds to high with warning if API rejects it
- [ ] Schemas with `additionalProperties` no longer rejected
- [ ] `uv run pytest tests/test_google_provider.py` passes
- [ ] Coverage for `src/tau_ai/google.py` >= 85%
