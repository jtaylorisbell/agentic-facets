"""Unit tests for the incident-scenario tools + fixture coherence.

The fixture is the ground truth every recipe shares, so these tests double as a guard that the
scenario stays internally consistent (logs, metrics, deployments, and DQ all agree).
"""


import tools
from facets.agents import ExecutionContext
from facets.approvals import ApprovalPolicy, AuthorityLevel
from tools import (
    all_tools,
    check_data_quality,
    get_pipeline_status,
    list_recent_deployments,
    query_logs,
    query_metrics,
    read_only_tools,
    restart_job,
    roll_back_deployment,
)
from tools._fixture import ROOT_CAUSE_PHRASE


def ctx(**kw):
    return ExecutionContext(task_id="incident-test", **kw)


async def test_query_logs_returns_error_line():
    logs = await query_logs.execute({"pipeline": "orders_daily"}, ctx())
    assert not logs.is_error
    text = logs.as_text()
    assert "SchemaValidationError" in text
    assert "amount" in text


async def test_query_logs_level_filter():
    errors = await query_logs.execute({"pipeline": "orders_daily", "level": "ERROR"}, ctx())
    assert all(e["level"] == "ERROR" for e in errors.content)
    assert len(errors.content) == 2


async def test_metrics_flag_regressions():
    result = await query_metrics.execute({"pipeline": "orders_daily"}, ctx())
    m = result.content
    assert m["rows_written"]["latest"] == 0
    assert m["rows_written"]["regressed"] is True
    assert m["error_rate"]["regressed"] is True


async def test_pipeline_status_failed():
    status = await get_pipeline_status.execute({"pipeline": "orders_daily"}, ctx())
    assert status.content["status"] == "FAILED"


async def test_deployments_include_culprit():
    deploys = await list_recent_deployments.execute({"pipeline": "orders_daily"}, ctx())
    ids = [d["id"] for d in deploys.content]
    assert "deploy-8842" in ids
    culprit = next(d for d in deploys.content if d["id"] == "deploy-8842")
    assert "STRING" in culprit["summary"]


async def test_data_quality_fails_on_amount():
    dq = await check_data_quality.execute({"pipeline": "orders_daily"}, ctx())
    assert dq.content["passed"] is False
    failed_cols = {c["column"] for c in dq.content["failed_checks"]}
    assert "amount" in failed_cols


async def test_unknown_pipeline_soft_errors():
    result = await query_logs.execute({"pipeline": "does_not_exist"}, ctx())
    assert result.is_error
    assert "Unknown pipeline" in result.as_text()


async def test_healthy_pipeline_has_no_incident():
    dq = await check_data_quality.execute({"pipeline": "clicks_hourly"}, ctx())
    assert dq.content["passed"] is True
    status = await get_pipeline_status.execute({"pipeline": "clicks_hourly"}, ctx())
    assert status.content["status"] == "SUCCEEDED"


# ---- Authority axis: remediation is gated -------------------------------------------------


async def test_restart_denied_without_policy():
    result = await restart_job.execute({"pipeline": "orders_daily"}, ctx())
    assert result.content["executed"] is False
    assert result.content["decision"] == "deny"


async def test_restart_denied_under_read_only_authority():
    policy = ApprovalPolicy(level=AuthorityLevel.ADVISORY)
    result = await restart_job.execute({"pipeline": "orders_daily"}, ctx(approvals=policy))
    assert result.content["executed"] is False


async def test_rollback_allowed_with_approval_and_audited():
    from facets.state import TaskState

    state = TaskState(task_id="incident-test")
    policy = ApprovalPolicy(
        level=AuthorityLevel.APPROVAL_GATED,
        gated_actions={"roll_back_deployment"},
        on_approval=lambda r: True,
    )
    result = await roll_back_deployment.execute(
        {"deployment_id": "deploy-8842"}, ctx(approvals=policy, state=state)
    )
    assert result.content["executed"] is True
    # Audit trail recorded on task state.
    assert len(state.approvals) == 1
    assert state.approvals[0]["action"] == "roll_back_deployment"


def test_toolsets_shape():
    assert len(read_only_tools()) == 5
    assert len(all_tools()) == 7
    names = {t.spec.name for t in all_tools()}
    assert {"restart_job", "roll_back_deployment"} <= names


def test_root_cause_phrase_present_in_fixture():
    incident = tools.INCIDENTS["orders_daily"]
    assert ROOT_CAUSE_PHRASE in incident["root_cause"].lower()
