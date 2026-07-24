# Recipes

Each recipe solves the **same incident** — a failed `orders_daily` data pipeline — and changes
**one FACETS axis** from the recipe before it. Every recipe is independently runnable and ships
the same set of files:

```text
NN_recipe_name/
├── README.md      # Problem → FACETS profile → what changed → walkthrough → failure lab → eval
├── facets.yaml    # machine-readable FACETS profile (schema-validated)
├── diagram.mmd    # architecture diagram (Mermaid)
├── app.py         # runnable: offline by default, --live for a Databricks endpoint
└── eval.yaml      # goal + ground truth for the comparison table
```

## The ladder

| Recipe | One-line idea | Axis changed |
|---|---|---|
| [00 · Deterministic baseline](00-deterministic-baseline.md) | Fixed code, no model — the control | — |
| [01 · Single tool agent](01-single-tool-agent.md) | Give the model the wheel | **Control** |
| [02 · Routed workflow](02-routed-workflow.md) | Classify, then dispatch to a specialist | **Execution / Topology** |
| [03 · Planner–executor](03-planner-executor.md) | Make the plan an explicit artifact | **Execution / State** |
| [04 · Parallel investigation](04-parallel-investigation.md) | Fan out independent work, fan in | **Execution** |
| [05 · Manager–worker](05-manager-worker.md) | Delegate to specialist agents | **Topology** |

Run any recipe:

```bash
uv run python recipes/01_single_tool_agent/app.py          # offline, deterministic
uv run python recipes/01_single_tool_agent/app.py --live   # live Databricks model
```

Compare them:

```bash
uv run python evals/run_evals.py
```

## Roadmap

Later releases fill in the rest of the ladder from the framework: handoffs (06), maker–checker /
reflection (07), durable event-driven execution (08), approval-gated actions (09), and a composed
production system (10).
