"""`query_logs` — read recent log lines for a pipeline. (Read-only, environmental source.)"""

from __future__ import annotations

from typing import Any

from facets.tools import tool

from ._fixture import get_incident


def query_logs_raw(pipeline: str, level: str | None = None) -> list[dict[str, Any]]:
    """Plain function form, callable directly by the deterministic baseline (recipe 00)."""
    logs = get_incident(pipeline)["logs"]
    if level:
        logs = [entry for entry in logs if entry["level"] == level.upper()]
    return logs


@tool(name="query_logs")
async def query_logs(pipeline: str, level: str = "") -> list[dict[str, Any]]:
    """Return recent log entries for a data pipeline.

    Args:
        pipeline: The pipeline name, e.g. 'orders_daily'.
        level: Optional level filter, one of INFO/WARN/ERROR. Empty means all levels.
    """
    return query_logs_raw(pipeline, level or None)
