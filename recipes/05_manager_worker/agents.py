"""Worker specialists for the manager–worker topology.

Each worker is an ordinary :class:`~facets.agents.Agent` with a *scoped* subset of the incident
tools and a narrow system prompt. The manager (in ``app.py``) delegates to them via
:func:`~facets.agents.agent_as_tool`, so from the manager's perspective a specialist is just
another callable tool that happens to be intelligent.

The distinction that makes this *manager–worker* and not *handoff* (Recipe 06): the manager
stays responsible. A worker runs in its own isolated context, returns a result, and control
returns to the manager — the worker never takes over the conversation.
"""

from __future__ import annotations

from facets.agents import Agent, Budget
from facets.models import FakeModel, ModelProvider, call
from tools import (
    check_data_quality,
    get_pipeline_status,
    list_recent_deployments,
    query_logs,
    query_metrics,
)


def log_worker(model: ModelProvider) -> Agent:
    return Agent(
        name="log_investigator",
        model=model,
        tools=[query_logs, get_pipeline_status],
        system_prompt=(
            "You investigate pipeline logs. Read the error logs and pipeline status, then report "
            "the single most important error line and what it implies. Be terse."
        ),
        budget=Budget(max_steps=4),
    )


def metrics_worker(model: ModelProvider) -> Agent:
    return Agent(
        name="metrics_investigator",
        model=model,
        tools=[query_metrics],
        system_prompt=(
            "You investigate pipeline metrics. Report which metrics regressed versus baseline "
            "(rows written, error rate, duration) and by how much. Be terse."
        ),
        budget=Budget(max_steps=3),
    )


def data_quality_worker(model: ModelProvider) -> Agent:
    return Agent(
        name="data_quality_investigator",
        model=model,
        tools=[check_data_quality],
        system_prompt=(
            "You investigate data-quality checks. Report which checks failed and on which "
            "columns, with the specific detail. Be terse."
        ),
        budget=Budget(max_steps=3),
    )


def deployment_worker(model: ModelProvider) -> Agent:
    return Agent(
        name="deployment_investigator",
        model=model,
        tools=[list_recent_deployments],
        system_prompt=(
            "You investigate recent deployments that could have caused a failure. Report the most "
            "suspicious recent deployment and why. Be terse."
        ),
        budget=Budget(max_steps=3),
    )


# --- Deterministic scripts for offline runs / tests ----------------------------------------
#
# Each worker gets its own short FakeModel plan: call its tool(s), then summarize. Because each
# worker runs in an isolated context, these scripts are independent of one another and of the
# manager's script.


def scripted_log_worker(pipeline: str) -> FakeModel:
    return FakeModel(
        script=[
            [call("query_logs", pipeline=pipeline, level="ERROR")],
            "Key error: SchemaValidationError on column 'amount' (expected DECIMAL, got STRING).",
        ]
    )


def scripted_metrics_worker(pipeline: str) -> FakeModel:
    return FakeModel(
        script=[
            [call("query_metrics", pipeline=pipeline)],
            "rows_written collapsed from 1.25M to 0; error_rate rose from 0.0 to 1.0.",
        ]
    )


def scripted_data_quality_worker(pipeline: str) -> FakeModel:
    return FakeModel(
        script=[
            [call("check_data_quality", pipeline=pipeline)],
            "Failed checks: 'amount' type_match (expected DECIMAL, observed STRING) and null_rate.",
        ]
    )


def scripted_deployment_worker(pipeline: str) -> FakeModel:
    return FakeModel(
        script=[
            [call("list_recent_deployments", pipeline=pipeline)],
            "Suspicious: deploy-8842 on orders_ingest changed 'amount' from DECIMAL to STRING.",
        ]
    )
