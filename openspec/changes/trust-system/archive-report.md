# Trust System — Archive Report

**Change:** `trust-system`
**Archive Date:** 2026-07-09
**Status:** **PASS — Archived**

---

## Executive Summary

The Trust System implements a persistent, user-controlled tool-trust layer for Tau's harness approval chain. When a tool's approval policy resolves to `"ask"`, the system consults a local trust store (`~/.tau/trust.json`) before blocking execution. Untrusted tools return a structured denial message naming the tool, its arguments, and instructions to trust it via `/trust add`. Trusted tools pass through without interruption.

The implementation is complete, verified, and ready for archival. All 10 acceptance criteria pass, 39 tests pass across 3 test files, and no unchecked implementation tasks remain.

---

## What Was Built & Why

### Problem

Tau's harness approval chain had three policy states — `allow`, `deny`, `ask` — but `"ask"` had no persistence: the user was prompted every time, with no way to say "remember my choice." This made iterative development with approval-gated tools friction-heavy.

### Solution

A trust store (JSON file at `~/.tau/trust.json`) that persists tool-trust decisions. The flow:

1. Harness resolves approval → `"ask"` for a tool
2. Trust store is consulted: if tool is trusted → tool runs (treated as `allow`)
3. If untrusted → structured denial with tool name, args, and `/trust add` guidance
4. User runs `/trust add <tool>` once → subsequent invocations proceed without interruption

Explicit `deny` policies always win, even if the tool is in the trust store. No harness config format changes were required.

---

## Files Changed

### New Files

| File | Lines | Purpose |
|------|-------|---------|
| `src/tau_coding/trust_store.py` | 145 | Core `TrustStore` dataclass (load/save/is_trusted/add/remove/list_trusted) + `format_ask_message()` for structured denial messages |
| `tests/test_trust_store.py` | 169 | 17 tests: load/save/corrupt file, add/remove/is_trusted, format_ask_message variants |
| `tests/test_trust_command.py` | 144 | 10 tests: `/trust add/remove/list/help` subcommands, edge cases (duplicate, nonexistent, missing args) |

### Modified Files

| File | Lines Changed | Purpose |
|------|---------------|---------|
| `src/tau_coding/tools.py` | +34/-9 | `_check_tool_approval` gains `arguments` parameter; trust store integration in `"ask"` branch; `_check_trust_store` helper; `_wrap_tool_with_events` passes arguments through |
| `src/tau_coding/commands.py` | +70 | New `_trust_command` handler with add/remove/list/help routing; `/trust` registered in `create_default_command_registry()` |
| `src/tau_coding/harness.py` | +8/-1 | `ApprovalAction` NamedTuple added after `HarnessApproval`; `NamedTuple` import |
| `tests/test_approval_chain.py` | +66/-7 | Old `test_ask_falls_through_to_allow` replaced with 4 trust-based tests (untrusted blocks, trusted allows, args in message, deny overrides trust); `TrustStore` path fixture |

---

## Key Design Decisions

1. **Trust store as a flat JSON file** (`~/.tau/trust.json`): Simple, human-editable, no database dependency, follows `TauPaths` conventions.
2. **No harness config changes**: Trust is a complementary layer — the existing `harness.toml` `allow`/`deny`/`ask` policies remain the first gate. Trust only activates on `"ask"`.
3. **Deny always wins**: Even a trusted tool is blocked if an explicit `deny` rule exists. Security-first: explicit opt-out overrides convenience opt-in.
4. **Graceful degradation**: Missing/corrupt `trust.json` initializes to an empty store — no crashes, no prompts about corruption.
5. **Structured denial messages**: Tool name, truncated args (max 3, long values truncated to 60 chars), and `/trust add` guidance in a single string.
6. **No agent loop changes**: All trust behavior is in `tau_coding` — the agent loop in `tau_agent` is untouched. The existing `AgentToolResult(ok=False, content=..., error=...)` pattern is sufficient.

---

## Verification Results

| Metric | Result |
|--------|--------|
| Acceptance criteria | **10/10 PASS** |
| Tests passing | **39/39** |
| Test files | 3: `test_trust_store.py` (17), `test_trust_command.py` (11), `test_approval_chain.py` (11) |
| Existing tests preserved | 8 harness/approval tests continue to pass unchanged |
| Edge cases covered | 13 (corrupt JSON, missing file, empty args, long args, >3 args, nonexistent tools, duplicate add, missing subcommand args, empty list, etc.) |
| Strict TDD | **Compliant** |

---

## Artifacts Read

| Artifact | Source | Retrieved |
|----------|--------|-----------|
| Proposal | Engram (`sdd/trust-system/proposal`) | ⚠️ Unavailable (server timeout) — reconstructed from spec Purpose |
| Spec | Engram (`sdd/trust-system/spec`, obs id: 17099) | ✅ |
| Design | Engram (`sdd/trust-system/design`) | ⚠️ Unavailable (server timeout) |
| Tasks | Engram (`sdd/trust-system/tasks`, obs id: 17101) | ✅ |
| Verify Report | `openspec/changes/trust-system/verify-report.md` | ✅ |

---

## Task Completion Gate

- [x] All implementation tasks checked (`[x]`) in persisted tasks artifact
- [x] No unchecked `[ ]` markers present
- [x] Verify report confirms all acceptance criteria pass
- [x] No stale-checkbox reconciliation needed

---

## Risks & Follow-Up Items

| Item | Priority | Note |
|------|----------|------|
| No concurrency guard on `TrustStore.save()` | Low | Single-user CLI tool; no concurrent writers expected |
| Trust store path hardcoded to `~/.tau/` | Low | Follows existing `TauPaths` convention |
| No tool-name validation in `/trust add` | Low | Accepts any string; no security implication, tools with spaces are uncommon |
| Future: GUI trust management | Future | `/trust list` + manual editing of `trust.json` sufficient for now |
| Future: Per-session trust (non-persistent) | Future | Not requested; all trust is persistent by design |

---

## Archived State (Engram)

This archive report is persisted in Engram at topic key `sdd/trust-system/archive-report` (observation id: 17104). The implementation is live in the codebase.
