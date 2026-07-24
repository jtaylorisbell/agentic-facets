# Recipes

Each recipe answers the **same OfficeQA question** — a hard, document-grounded question from the
U.S. Treasury Bulletin corpus — and changes **one FACETS axis** from the recipe before it. Every
recipe is independently runnable and ships the same set of files:

```text
NN_recipe_name/
├── README.md      # Problem → FACETS profile → what changed → walkthrough → failure lab → eval
├── facets.yaml    # machine-readable FACETS profile (schema-validated)
├── diagram.mmd    # architecture diagram (Mermaid)
├── app.py         # runnable; answers a question with a real model, scored by reward.py
└── eval.yaml      # the OfficeQA question uids to run
```

## The ladder

| Recipe | One-line idea | Axis changed |
|---|---|---|
| [00 · Closed-book baseline](00-closed-book-baseline.md) | Ask the model directly, no tools — the control | — |
| [01 · Single document agent](01-single-tool-agent.md) | Give the model document tools and the wheel | **Control** |
| [02 · Routed workflow](02-routed-workflow.md) | Classify the question type, dispatch to a specialist | **Execution / Topology** |
| [03 · Planner–executor](03-planner-executor.md) | Make the plan an explicit artifact | **Execution / State** |
| [04 · Parallel investigation](04-parallel-investigation.md) | One reader per document, fan out / fan in | **Execution** |
| [05 · Manager–worker](05-manager-worker.md) | Delegate to a researcher + a calculator | **Topology** |

Run any recipe (needs credentials — see the [quick start](../index.md#quick-start)):

```bash
uv run python recipes/01_single_tool_agent/app.py
uv run python recipes/01_single_tool_agent/app.py --uid UID0056
```

Compare them:

```bash
uv run python evals/run_evals.py
```

## Oracle retrieval

OfficeQA ships the gold `source_files` for each question, and the recipes scope their document
tools to those files. That is deliberate: the cookbook teaches agent **architecture**, so we hand
the agent the right documents and let the architecture differences show up in how it *reasons over*
them — not in whether it can solve the separate retrieval problem. A production system would add a
real retrieval tool over the full 697-document corpus.

## Roadmap

Later releases fill in the rest of the ladder from the framework: handoffs (06), maker–checker /
reflection (07), durable event-driven execution (08), approval-gated actions (09), and a composed
production system (10).
