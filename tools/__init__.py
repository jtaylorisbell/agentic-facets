"""Incident-scenario tools for the Agentic FACETS cookbook.

All tools operate over a single seeded fixture (:mod:`tools._fixture`) so investigations are
deterministic and offline. Read-only tools inspect the world; the remediation tools act on it
and are gated by the approval policy.

Convenience collections:

* :func:`read_only_tools` — the four investigation tools (logs, metrics, pipelines/deployments,
  data quality). What a read-only investigator gets.
* :func:`all_tools` — read-only tools plus the gated remediation actions.
"""

from __future__ import annotations

from facets.tools import Tool

from ._fixture import DEFAULT_PIPELINE, INCIDENTS, ROOT_CAUSE_PHRASE
from .data_quality import check_data_quality, check_data_quality_raw
from .logs import query_logs, query_logs_raw
from .metrics import query_metrics, query_metrics_raw
from .pipelines import (
    get_pipeline_status,
    get_pipeline_status_raw,
    list_recent_deployments,
    list_recent_deployments_raw,
)
from .remediation import restart_job, roll_back_deployment

__all__ = [
    "DEFAULT_PIPELINE",
    "ROOT_CAUSE_PHRASE",
    "INCIDENTS",
    "query_logs",
    "query_metrics",
    "get_pipeline_status",
    "list_recent_deployments",
    "check_data_quality",
    "restart_job",
    "roll_back_deployment",
    "query_logs_raw",
    "query_metrics_raw",
    "get_pipeline_status_raw",
    "list_recent_deployments_raw",
    "check_data_quality_raw",
    "read_only_tools",
    "all_tools",
]


def read_only_tools() -> list[Tool]:
    """The investigation toolset — safe to hand any agent; takes no consequential actions."""
    return [
        query_logs,
        query_metrics,
        get_pipeline_status,
        list_recent_deployments,
        check_data_quality,
    ]


def all_tools() -> list[Tool]:
    """Read-only tools plus the gated remediation actions."""
    return [*read_only_tools(), restart_job, roll_back_deployment]
