# Proposal: Session Insights Sidebar

## Intent

The TUI sidebar shows provider, model, tools, skills, and context — but gives no feedback on how many turns were used, how many tool calls were made, how many tokens were consumed, or what the session cost. Users run blind on usage. Add a "Stats" section with derivable estimates from existing session data.

## Scope

### In Scope
- New `session_stats.py` module — derives turn count, tool calls, input/output token estimates, and estimated cost from in-memory message data
- Extend `SessionSummarySource` protocol with stats fields
- Extend sidebar render (`render_session_sidebar`) with a "Stats" section
- Connect `CodingSession` stats via the protocol
- Unit tests for `session_stats.py`

### Out of Scope
- Real usage tracking from provider APIs (token-usage headers, cost fields)
- Token/bandwidth monitoring over time or per-turn breakdowns
- Cost tracking across sessions or export
- Per-model cost-tier selection in the UI (uses catalog defaults)
- Stats section in `CompactSessionInfo`

## Capabilities

### New Capabilities
- `session-insights`: Derivable session stats (turn count, tool calls, token estimates, cost estimate) exposed through the sidebar.

### Modified Capabilities
- None — pure additive; no spec-level behavior changes to existing capabilities.

## Approach

Hybrid: derive what we can now, defer provider API usage tracking.

1. **`session_stats.py`**: Functions that accept `tuple[AgentMessage, ...]` and compute:
   - `turn_count` = number of `AssistantMessage` entries (multi-turn tool call groups count as 1)
   - `tool_call_count` = sum of `len(msg.tool_calls)` across all `AssistantMessage` entries
   - `input_token_estimate` = `estimate_context_usage()` for messages
   - `output_token_estimate` = `sum(len(msg.content) / 4 for msg in AssistantMessage)`
   - `cost_estimate` = `model_cost_for_input_tokens()` on input + similar output tier lookup
2. **Protocol** (`SessionSummarySource`): Add `stats: SessionStats` property with a frozen dataclass.
3. **`CodingSession`**: Implement `stats` by calling `session_stats.compute(message, model, provider_name)`.
4. **Sidebar render**: Add "Stats" section after "session" showing turns, tool calls, token usage, and cost. All estimates labelled with `~`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/tau_coding/session_stats.py` | **New** | Derivative stats module |
| `src/tau_coding/tui/sidebar.py` | Modify | Protocol + render |
| `src/tau_coding/session.py` | Modify | Wire stat property |
| `tests/test_session_stats.py` | **New** | Unit tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Estimate drift (token/cost) | Medium | Label outputs `~`; docstring caveats |
| Performance scanning messages on each render | Low | Operates on in-memory tuple; O(n) scan of ~hundreds, not thousands |
| Provider without catalog cost data | Low | Show `--` when cost data unavailable |

## Rollback Plan

Revert protocol changes in `sidebar.py` and `session.py`. Remove `session_stats.py`. No data migration needed — additive change only.

## Dependencies

- `context_window.estimate_context_usage()` and `CHARS_PER_TOKEN` (existing)
- `provider_catalog.model_cost_for_input_tokens()` and `builtin_provider_entry()` (existing)

## Success Criteria

- [ ] Sidebar shows "turns: N" and "tools: N calls" in a new Stats section
- [ ] Token usage shows estimated input/output with `~` prefix
- [ ] Cost shows estimated value or `--` when data unavailable
- [ ] `session_stats.py` has >80% line coverage
