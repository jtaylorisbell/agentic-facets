"""`check_data_quality` — run the pipeline's data-quality checks. (Read-only.)"""

from __future__ import annotations

from typing import Any

from facets.tools import tool

from ._fixture import get_incident


def check_data_quality_raw(pipeline: str) -> dict[str, Any]:
    checks = get_incident(pipeline)["data_quality"]
    failed = [c for c in checks if not c["passed"]]
    return {
        "pipeline": pipeline,
        "checks": checks,
        "failed_checks": failed,
        "passed": len(failed) == 0,
    }


@tool(name="check_data_quality")
async def check_data_quality(pipeline: str) -> dict[str, Any]:
    """Run data-quality checks for a pipeline and summarize which passed or failed.

    Args:
        pipeline: The pipeline name, e.g. 'orders_daily'.
    """
    return check_data_quality_raw(pipeline)
