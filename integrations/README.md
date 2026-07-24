# Integrations

The Agentic FACETS core runtime (`src/facets/`) is **framework-neutral by design** — plain
Python, no agent framework required. That is deliberate: it teaches the difference between an
*architectural pattern* and a *framework implementation of that pattern*.

> The architecture stays constant while the runtime changes.

This directory is where framework adapters live. Each adapter re-implements the *same* FACETS
recipes on top of a specific framework, so a reader can compare a pattern across runtimes:

```text
integrations/
├── openai_agents/     # OpenAI Agents SDK
├── langgraph/         # LangGraph
├── databricks/        # Databricks agent framework + MLflow
└── semantic_kernel/   # Semantic Kernel
```

A recipe may then provide several equivalent implementations:

```text
implementation/
├── plain_python.py    # the framework-neutral version (shipped today)
├── openai_agents.py
└── langgraph.py
```

## Status

Not yet implemented. Release 0.1 ships the framework-neutral core and recipes only; adapters
come in a later release once the core patterns are stable. The one "real runtime" wired up today
is the [`DatabricksModel`](../src/facets/models.py) provider, which talks to Databricks
foundation-model endpoints over their OpenAI-compatible surface — see
[`infrastructure/databricks/`](../infrastructure/databricks/).
