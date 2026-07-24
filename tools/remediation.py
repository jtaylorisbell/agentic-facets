"""`restart_job` and `roll_back_deployment` — the *action* tools (Authority axis).

Unlike the read-only investigation tools, these change the world. They demonstrate the
framework's core rule: **the prompt is never the authorization boundary.** Each action asks the
:class:`~facets.approvals.ApprovalPolicy` on the :class:`~facets.agents.ExecutionContext`
before doing anything; if no policy is attached, the action fails safe (denied).

In Release 0.1 these are wired but exercised lightly. The full approval-gated flow — risk-based
policies, human callbacks, audit trails, post-action verification, compensating actions — is
recipe 09.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from facets.approvals import ApprovalRequest, Decision
from facets.tools import tool

from ._fixture import get_incident

if TYPE_CHECKING:
    from facets.agents import ExecutionContext


def _run_action(
    action: str, arguments: dict[str, Any], context: ExecutionContext
) -> dict[str, Any]:
    """Shared gate + execute + audit path for every action tool."""
    request = ApprovalRequest(
        action=action, arguments=arguments, reason=f"Agent requested {action}."
    )

    policy = context.approvals
    if policy is None:
        return {
            "action": action,
            "executed": False,
            "decision": "deny",
            "detail": "No approval policy attached — actions are denied by default (fail-safe).",
        }

    decision = policy.evaluate(request)
    record = {
        "action": action,
        "arguments": arguments,
        "decision": decision.decision.value,
        "rationale": decision.rationale,
        "approver": decision.approver,
    }
    # Audit trail: every attempt is recorded on task state, approved or not.
    if context.state is not None:
        context.state.approvals.append(record)

    if decision.decision is not Decision.ALLOW:
        return {**record, "executed": False}

    # "Execute" the action against the fixture world (no real side effects).
    return {**record, "executed": True, "detail": f"{action} completed successfully."}


@tool(name="restart_job")
async def restart_job(pipeline: str, context: ExecutionContext) -> dict[str, Any]:
    """Restart a failed pipeline job. Consequential — subject to the approval policy.

    Args:
        pipeline: The pipeline whose job should be restarted, e.g. 'orders_daily'.
    """
    get_incident(pipeline)  # validate the target exists before proposing an action
    return _run_action("restart_job", {"pipeline": pipeline}, context)


@tool(name="roll_back_deployment")
async def roll_back_deployment(deployment_id: str, context: ExecutionContext) -> dict[str, Any]:
    """Roll back a deployment. Consequential — subject to the approval policy.

    Args:
        deployment_id: The deployment to roll back, e.g. 'deploy-8842'.
    """
    return _run_action("roll_back_deployment", {"deployment_id": deployment_id}, context)
