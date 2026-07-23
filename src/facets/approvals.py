"""Approvals: the FACETS **Authority** axis — *what the system may do independently*.

The load-bearing idea from the framework: **prompts must never be the only authorization
boundary for consequential actions.** Authority is enforced in code, outside the model. An
action tool asks the :class:`ApprovalPolicy` before it executes; the policy — not the prompt —
decides whether the action proceeds, is denied, or requires a human.

Release 0.1 defines these types and uses them lightly (the remediation tool is gated). The
full approval-gated action flow with audit trails is recipe 09.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AuthorityLevel(StrEnum):
    """The escalating levels from the framework's Authority axis."""

    ADVISORY = "advisory"  # may only recommend
    DRAFTING = "drafting"  # may draft, not send
    APPROVAL_GATED = "approval-gated"  # may act only after explicit approval
    BOUNDED_AUTONOMOUS = "bounded-autonomous"  # may act within fixed limits
    BROAD_AUTONOMOUS = "broad-autonomous"  # may act freely


class Decision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require-approval"


class ApprovalRequest(BaseModel):
    """A request to perform a consequential action, evaluated by the policy."""

    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class ApprovalDecision(BaseModel):
    decision: Decision
    rationale: str = ""
    approver: str | None = None


# A human-approval callback: given a request, return True to approve. Defaults to auto-deny so
# that "no approver wired up" fails safe rather than silently executing.
ApprovalCallback = Callable[[ApprovalRequest], bool]


def _auto_deny(_: ApprovalRequest) -> bool:
    return False


class ApprovalPolicy:
    """Decides whether an action may proceed, based on authority level and per-action rules.

    * ``allowed_actions`` — actions permitted without human sign-off (within the level).
    * ``gated_actions``   — actions that always require human approval.
    * ``on_approval``     — callback invoked for gated actions (auto-deny by default).
    """

    def __init__(
        self,
        level: AuthorityLevel = AuthorityLevel.DRAFTING,
        *,
        allowed_actions: set[str] | None = None,
        gated_actions: set[str] | None = None,
        on_approval: ApprovalCallback | None = None,
    ):
        self.level = level
        self.allowed_actions = allowed_actions or set()
        self.gated_actions = gated_actions or set()
        self._on_approval = on_approval or _auto_deny

    def evaluate(self, request: ApprovalRequest) -> ApprovalDecision:
        action = request.action

        # Read-only postures never permit consequential actions.
        if self.level in (AuthorityLevel.ADVISORY, AuthorityLevel.DRAFTING):
            return ApprovalDecision(
                decision=Decision.DENY,
                rationale=f"Authority level '{self.level.value}' may not execute actions.",
            )

        if self.level is AuthorityLevel.BROAD_AUTONOMOUS:
            return ApprovalDecision(decision=Decision.ALLOW, rationale="Broad autonomy.")

        # Bounded/approval-gated: explicit allow-list acts freely; gated actions need a human.
        if action in self.allowed_actions and action not in self.gated_actions:
            return ApprovalDecision(decision=Decision.ALLOW, rationale="Within allowed actions.")

        if action in self.gated_actions or self.level is AuthorityLevel.APPROVAL_GATED:
            approved = self._on_approval(request)
            return ApprovalDecision(
                decision=Decision.ALLOW if approved else Decision.DENY,
                rationale="Human approval " + ("granted." if approved else "denied."),
                approver="human",
            )

        return ApprovalDecision(
            decision=Decision.DENY, rationale=f"Action '{action}' is not permitted."
        )
