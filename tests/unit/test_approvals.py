"""Unit tests for the Authority axis: authority levels and per-action gating."""

from facets.approvals import (
    ApprovalPolicy,
    ApprovalRequest,
    AuthorityLevel,
    Decision,
)


def req(action="restart_job", **args):
    return ApprovalRequest(action=action, arguments=args)


def test_read_only_levels_deny_actions():
    for level in (AuthorityLevel.ADVISORY, AuthorityLevel.DRAFTING):
        policy = ApprovalPolicy(level=level)
        assert policy.evaluate(req()).decision is Decision.DENY


def test_broad_autonomous_allows():
    policy = ApprovalPolicy(level=AuthorityLevel.BROAD_AUTONOMOUS)
    assert policy.evaluate(req()).decision is Decision.ALLOW


def test_bounded_allows_listed_action():
    policy = ApprovalPolicy(
        level=AuthorityLevel.BOUNDED_AUTONOMOUS,
        allowed_actions={"restart_job"},
    )
    assert policy.evaluate(req()).decision is Decision.ALLOW


def test_gated_action_requires_human_and_auto_denies():
    # No approval callback wired up => fails safe (deny).
    policy = ApprovalPolicy(
        level=AuthorityLevel.BOUNDED_AUTONOMOUS,
        allowed_actions={"restart_job"},
        gated_actions={"restart_job"},
    )
    decision = policy.evaluate(req())
    assert decision.decision is Decision.DENY
    assert decision.approver == "human"


def test_gated_action_allows_when_human_approves():
    policy = ApprovalPolicy(
        level=AuthorityLevel.APPROVAL_GATED,
        gated_actions={"restart_job"},
        on_approval=lambda r: True,
    )
    assert policy.evaluate(req()).decision is Decision.ALLOW


def test_approval_gated_level_gates_everything():
    policy = ApprovalPolicy(level=AuthorityLevel.APPROVAL_GATED, on_approval=lambda r: False)
    assert policy.evaluate(req("delete_table")).decision is Decision.DENY
