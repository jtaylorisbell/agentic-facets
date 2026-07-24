"""`get_pipeline_status` and `list_recent_deployments` — pipeline + deploy history. (Read-only.)"""

from __future__ import annotations

from typing import Any

from facets.tools import tool

from ._fixture import get_incident


def get_pipeline_status_raw(pipeline: str) -> dict[str, Any]:
    return dict(get_incident(pipeline)["pipeline"])


def list_recent_deployments_raw(pipeline: str) -> list[dict[str, Any]]:
    return list(get_incident(pipeline)["deployments"])


@tool(name="get_pipeline_status")
async def get_pipeline_status(pipeline: str) -> dict[str, Any]:
    """Return the current status of a pipeline (state, last run, last success, owner, schedule).

    Args:
        pipeline: The pipeline name, e.g. 'orders_daily'.
    """
    return get_pipeline_status_raw(pipeline)


@tool(name="list_recent_deployments")
async def list_recent_deployments(pipeline: str) -> list[dict[str, Any]]:
    """List recent deployments that could affect a pipeline, most recent first.

    Args:
        pipeline: The pipeline name, e.g. 'orders_daily'.
    """
    return list_recent_deployments_raw(pipeline)
