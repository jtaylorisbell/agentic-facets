"""The canonical incident scenario — a seeded, internally-consistent world.

Every tool in this package reads from this fixture, so an investigation *coheres*: the logs,
metrics, deployment history, and data-quality checks all point at the same root cause. That
lets the cookbook run the *same* incident through every recipe (deterministic baseline, single
agent, manager–worker, …) and compare architectures on identical ground truth — with no
network and no nondeterminism.

The canonical incident (`orders_daily`):

    A deployment (`deploy-8842`) to the upstream `orders_ingest` service changed the `amount`
    field from DECIMAL to STRING. The next `orders_daily` run failed schema validation, wrote
    zero rows, and tripped the data-quality type check. **Root cause: a schema mismatch on the
    `amount` column introduced by an upstream deployment.**

A second, healthy pipeline (`clicks_hourly`) is included so tools can demonstrate the
"nothing wrong here" branch without special-casing.
"""

from __future__ import annotations

from typing import Any

# The phrase graders and scripted demos key on. Kept in one place so tools and evals agree.
ROOT_CAUSE_PHRASE = "schema mismatch"

INCIDENTS: dict[str, dict[str, Any]] = {
    "orders_daily": {
        "pipeline": {
            "name": "orders_daily",
            "status": "FAILED",
            "last_run": "2026-07-23T02:14:00Z",
            "last_success": "2026-07-22T02:12:00Z",
            "owner": "data-platform",
            "schedule": "0 2 * * *",
        },
        "logs": [
            {"ts": "2026-07-23T02:14:03Z", "level": "INFO", "msg": "Starting orders_daily run."},
            {"ts": "2026-07-23T02:14:07Z", "level": "INFO", "msg": "Reading source orders_ingest."},
            {
                "ts": "2026-07-23T02:14:09Z",
                "level": "ERROR",
                "msg": (
                    "SchemaValidationError: column 'amount' expected DECIMAL(18,2) "
                    "but received STRING. Aborting transform."
                ),
            },
            {
                "ts": "2026-07-23T02:14:09Z",
                "level": "ERROR",
                "msg": "Run failed after 0 rows written (exit code 1).",
            },
        ],
        "metrics": {
            "rows_written": {"latest": 0, "baseline": 1_250_000, "unit": "rows"},
            "error_rate": {"latest": 1.0, "baseline": 0.0, "unit": "fraction"},
            "duration_s": {"latest": 9, "baseline": 512, "unit": "seconds"},
        },
        "deployments": [
            {
                "id": "deploy-8842",
                "service": "orders_ingest",
                "ts": "2026-07-23T02:10:00Z",
                "summary": "Change `amount` field type from DECIMAL to STRING in ingest schema.",
                "author": "upstream-team",
            },
            {
                "id": "deploy-8830",
                "service": "orders_daily",
                "ts": "2026-07-21T15:02:00Z",
                "summary": "Bump transform image to 1.9.2 (no schema changes).",
                "author": "data-platform",
            },
        ],
        "data_quality": [
            {
                "column": "amount",
                "check": "type_match",
                "passed": False,
                "detail": "expected DECIMAL(18,2), observed STRING",
            },
            {
                "column": "amount",
                "check": "null_rate",
                "passed": False,
                "detail": "null rate 1.00 (baseline 0.001) — column failed to parse",
            },
            {"column": "order_id", "check": "uniqueness", "passed": True, "detail": "ok"},
        ],
        "root_cause": (
            "A schema mismatch on the `amount` column: upstream deployment deploy-8842 changed "
            "its type from DECIMAL to STRING, so orders_daily failed schema validation and wrote "
            "zero rows."
        ),
        "recommended_remediation": {
            "action": "roll_back_deployment",
            "target": "deploy-8842",
            "note": (
                "Restarting the job alone will not help while the upstream schema is wrong; "
                "roll back deploy-8842 or coordinate a compatible schema change, then rerun."
            ),
        },
    },
    "clicks_hourly": {
        "pipeline": {
            "name": "clicks_hourly",
            "status": "SUCCEEDED",
            "last_run": "2026-07-23T03:00:00Z",
            "last_success": "2026-07-23T03:00:00Z",
            "owner": "growth",
            "schedule": "0 * * * *",
        },
        "logs": [
            {"ts": "2026-07-23T03:00:01Z", "level": "INFO", "msg": "Starting clicks_hourly run."},
            {"ts": "2026-07-23T03:00:44Z", "level": "INFO", "msg": "Wrote 84,120 rows. Done."},
        ],
        "metrics": {
            "rows_written": {"latest": 84_120, "baseline": 83_400, "unit": "rows"},
            "error_rate": {"latest": 0.0, "baseline": 0.0, "unit": "fraction"},
            "duration_s": {"latest": 43, "baseline": 47, "unit": "seconds"},
        },
        "deployments": [],
        "data_quality": [
            {"column": "click_id", "check": "uniqueness", "passed": True, "detail": "ok"},
        ],
        "root_cause": None,
        "recommended_remediation": None,
    },
}

DEFAULT_PIPELINE = "orders_daily"


def get_incident(pipeline: str) -> dict[str, Any]:
    """Look up an incident by pipeline name, raising a clear error for unknown pipelines."""
    incident = INCIDENTS.get(pipeline)
    if incident is None:
        known = ", ".join(sorted(INCIDENTS))
        raise KeyError(f"Unknown pipeline '{pipeline}'. Known pipelines: {known}.")
    return incident
