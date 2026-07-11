"""Tool-approval-chain and trust-store helpers for Tau coding tools.

Extracted from tools.py to reduce module size.
"""

from __future__ import annotations

from collections.abc import Mapping

from tau_agent.types import JSONValue
from tau_coding.harness import HarnessApproval
from tau_coding.trust_store import TrustStore, format_ask_message


def _check_tool_approval(
    tool_name: str,
    approval: HarnessApproval | None,
    arguments: Mapping[str, JSONValue] | None = None,
) -> str | None:
    """Check if a tool is approved by the harness policy.

    Returns ``None`` if the tool may execute, or a denial reason string
    if the tool is blocked.

    Resolution order:
      1. Explicit rule for *tool_name* in ``approval.rules``
      2. ``approval.default`` ("allow", "deny", or "ask")
      3. No policy → allow
    """
    if approval is None:
        return None

    # 1. Explicit per-tool rule (wins over default)
    if tool_name in approval.rules:
        rule = approval.rules[tool_name]
        if rule == "deny":
            return f"Tool '{tool_name}' is denied by harness approval policy"
        if rule == "allow":
            return None
        # rule == "ask" → consult trust store
        return _check_trust_store(tool_name, arguments)

    # 2. Default policy
    if approval.default == "deny":
        return f"Tool '{tool_name}' is denied by default harness approval policy"
    if approval.default == "allow":
        return None

    # default == "ask" → consult trust store
    return _check_trust_store(tool_name, arguments)


def _check_trust_store(
    tool_name: str,
    arguments: Mapping[str, JSONValue] | None = None,
) -> str | None:
    """Consult the trust store for an ``"ask"``-resolved tool.

    Returns ``None`` if the tool is trusted, or a formatted denial
    message with trust guidance if not.
    """
    store = TrustStore.load()
    if store.is_trusted(tool_name):
        return None
    return format_ask_message(tool_name, arguments)
