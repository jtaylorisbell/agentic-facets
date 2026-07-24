# Databricks Production Track

A Databricks implementation gives Agentic FACETS an **enterprise-oriented, governed production
path** without making the framework itself vendor-specific. The core runtime stays neutral;
Databricks is layered on as a strong production implementation.

## What's wired up today (Release 0.1)

The model layer. [`facets.models.DatabricksModel`](../../src/facets/models.py) talks to a
Databricks **foundation-model serving endpoint** through its OpenAI-compatible surface:

- **Base URL:** `{DATABRICKS_HOST}/serving-endpoints`
- **Auth:** `Authorization: Bearer {DATABRICKS_TOKEN}`
- **Model:** the serving-endpoint name — e.g. `databricks-claude-sonnet-4-6`, `databricks-gpt-5`

Because it's OpenAI-compatible, the adapter is a thin wrapper over the `openai` async client;
tool calling flows through the standard `tools=[...]` / `tool_calls` fields. Any recipe runs
against it with `--live`:

```bash
cp ../../.env.example ../../.env    # DATABRICKS_HOST, DATABRICKS_TOKEN, FACETS_MODEL
uv run python recipes/01_single_tool_agent/app.py --live
```

## The full track (roadmap)

The framework's axes map cleanly onto governed Databricks primitives. These are targeted for the
1.0 production track alongside Recipes 08–10:

| Concern | Databricks implementation |
|---|---|
| Agent tracing | MLflow |
| Evaluation | MLflow evaluation and scorers |
| Governed data tools | Unity Catalog functions |
| Transactional task state | Lakebase |
| Analytics and history | Delta tables |
| Secrets and identity | Databricks service principals |
| Application UI and API | Databricks Apps |
| Serving | Model Serving or Apps |
| Authorization | Unity Catalog and workspace permissions |

The design intent: keep the core framework neutral, then show Databricks as the reference for
*governed, auditable, production* agents — MLflow-traced, Unity-Catalog-governed tools,
Lakebase-durable task state, approval workflows, and full auditability.
