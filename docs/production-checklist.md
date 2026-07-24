# Production Checklist

A recipe's *minimal* implementation shows the pattern. A *production* implementation adds the
things that keep it alive under load and scrutiny. Walk the FACETS axes and ask, for each:

## Feedback

- [ ] Is success checked against the **environment**, not just the model's own say-so?
- [ ] Are there deterministic validators (schemas, row counts, types) where possible?
- [ ] For subjective outputs, is there a critic and/or human review path?

## Authority

- [ ] Is every consequential action gated by a **policy enforced in code**, not the prompt?
- [ ] Are permissions scoped per-tool (least privilege)?
- [ ] Is there an **audit trail** of what was attempted, approved, and executed?
- [ ] Are there **compensating actions** for anything that can't be un-done cleanly?

## Control

- [ ] Is the loop **bounded** (`max_steps`, token budget, wall-clock timeout)?
- [ ] Are the allowed tools explicitly enumerated?
- [ ] Does a hit limit produce a graceful, labeled outcome (not a hang or a crash)?

## Execution

- [ ] Retries with backoff on transient tool/model failures?
- [ ] Idempotency for anything that writes or triggers side effects?
- [ ] Timeouts on every external call?

## Topology

- [ ] Is the agent count **justified** — can a single agent demonstrably not do it?
- [ ] Are delegation contracts (worker inputs/outputs) explicit and validated?
- [ ] Is there loop/escalation protection in handoff systems?

## State

- [ ] Is task state **durable** if the work must survive interruption?
- [ ] Are checkpoints written so a resumed run doesn't repeat side effects?
- [ ] Is the **source of truth** unambiguous (the DB / repo / ticket system, not the transcript)?

## Observability

- [ ] Is every model and tool call **traced** with cost and latency?
- [ ] Are evaluations run in CI against a fixed dataset to catch regressions?

---

## Where this cookbook is today

Release 0.1 ships the framework, the runtime primitives, and Recipes 00 / 01 / 05 with offline,
deterministic evaluation. The production concerns above map onto later recipes:

| Concern | Recipe (roadmap) |
|---|---|
| Maker–checker / reflection | 07 |
| Durable, event-driven, resumable execution | 08 |
| Approval-gated actions, audit trails, compensations | 09 |
| Composed production system | 10 |

## Databricks production track

The runtime is framework-neutral by design. A Databricks implementation provides an
enterprise-oriented path without making the framework vendor-specific — MLflow for tracing and
evaluation, Unity Catalog functions for governed tools, Lakebase for durable task state, Delta
for history, and Databricks Apps for the UI. Release 0.1 wires the model layer to Databricks
foundation-model endpoints (the OpenAI-compatible serving surface); see
[`infrastructure/databricks/`](https://github.com/jtaylorisbell/agentic-facets/tree/main/infrastructure/databricks).
