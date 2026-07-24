"""`query_metrics` — compare a pipeline's latest metrics against baseline. (Read-only.)"""

from __future__ import annotations

from typing import Any

from facets.tools import tool

from ._fixture import get_incident


def query_metrics_raw(pipeline: str) -> dict[str, Any]:
    """Plain function form for the deterministic baseline.

    Annotates each metric with a ``regressed`` flag so downstream code (or a model) can spot
    the anomaly without re-deriving the comparison.
    """
    metrics = get_incident(pipeline)["metrics"]
    out: dict[str, Any] = {}
    for name, m in metrics.items():
        regressed = m["latest"] != m["baseline"]
        # For rows_written, "regressed" specifically means a drop; for error/duration, any rise.
        out[name] = {**m, "regressed": regressed}
    return out


@tool(name="query_metrics")
async def query_metrics(pipeline: str) -> dict[str, Any]:
    """Return latest-vs-baseline metrics for a pipeline (rows written, error rate, duration).

    Args:
        pipeline: The pipeline name, e.g. 'orders_daily'.
    """
    return query_metrics_raw(pipeline)
