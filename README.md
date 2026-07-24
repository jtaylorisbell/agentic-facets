# Agentic FACETS

A code cookbook for agent architectures. We take one hard question, answer it six different ways,
change exactly one design decision each time, and measure what each change buys. That's the whole
idea.

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)

---

## The problem

Here's a real question from the [OfficeQA benchmark](https://github.com/databricks/officeqa), which
grades models on hard questions grounded in U.S. Treasury Bulletins:

> As of the January 1980 ownership survey, how many investor-type categories held more than
> \$200 million?

The true answer is **2**. It lives in a table inside a specific 1980 Treasury Bulletin — you find
the ownership-survey table, read the seven category rows, and count the ones over the threshold.

We're going to answer this exact question several times. The first attempt uses no tools at all —
on purpose. By the end you'll know when that's the right call and when it isn't.

## Start with the dumbest possible thing

Whenever I'm tempted to reach for an "agent," I like to first ask what the dumbest version looks
like. Here it's: just ask the model the question. No documents, no tools, no magic. One call.

```bash
uv sync
cp .env.example .env    # fill in DATABRICKS_TOKEN + HF_TOKEN (see "Running it" below)
uv run python recipes/00_closed_book_baseline/app.py
```

```text
Q (UID0121): …how many investor-type categories held more than $200 million…?
Ground truth: 2
Answer:  <FINAL_ANSWER>6</FINAL_ANSWER>
Score:   INCORRECT  (extracted '6' vs truth '2')
Trace:   model_calls=1
```

Wrong. And that's not a bug — it's the honest result, and it's the whole reason the rest of the
repo exists. No model has a 1980 Treasury Bulletin ownership table memorized, so asked cold, it
produces a confident, plausible, wrong number. That single limitation is exactly what the next
version fixes. Nothing more.

## Change one thing: let the model read the documents

Now give the *same question* to a single agent, plus four tools — list the source documents,
search one, read a slice of one, and a calculator — and let the model decide which to call, in
what order, and when it has enough to answer. We changed exactly one decision: who's driving.

```bash
uv run python recipes/01_single_tool_agent/app.py
```

```text
Answer:  …only 2 categories held more than $200 million. <FINAL_ANSWER>2</FINAL_ANSWER>
Score:   CORRECT  (extracted '2' vs truth '2')
Trace:   model_calls=5, tool_calls=[list_source_documents, search_document, read_document, compute, compute]
```

Correct. Stare at the trace for a second. The baseline made 1 model call and guessed; this made
5, and actually *read the table* — it searched the document for the ownership survey, read the
rows, used the calculator to check each category against the \$200M threshold, and counted. What
we bought is grounding. What we paid is calls, tokens, latency, and a real chance the model reads
the wrong row.

That's the entire repo in two runs: **an architecture is a set of decisions, and every decision
has a price you can read off a trace.** "Who chooses the next step?" was just the first one. There
are five more.

## The six decisions: FACETS

Once you start naming these decisions, it turns out six of them cover almost every agent system
you'll meet. The nice part: they're independent. You can change one and leave the other five
alone — which is exactly what the recipes do.

| | Axis | The decision |
|---|---|---|
| **F** | Feedback | How does it know whether it succeeded? |
| **A** | Authority | What may it do on its own, without a human? |
| **C** | Control | Who chooses the next step — code, or the model? |
| **E** | Execution | How does work progress — sequential, parallel, planned? |
| **T** | Topology | One agent, or several, and who's in charge? |
| **S** | State | What persists, and where does truth actually live? |

Going from the baseline to the single agent moved exactly **one** axis: Control, from
code-directed to model-directed (and it dragged Feedback and document access along). Every recipe
plays the same game — change one axis from the recipe before it. Keep five fixed, wiggle one, and
any difference in the results is on that one change. No confounds.

```mermaid
flowchart LR
    R0["00 · Closed-book<br/>baseline"]
    R1["01 · Single<br/>document agent"]
    R2["02 · Routed<br/>workflow"]
    R3["03 · Planner–<br/>executor"]
    R4["04 · Parallel<br/>investigation"]
    R5["05 · Manager–<br/>worker"]
    R0 -->|"Control:<br/>code → model"| R1
    R1 -->|"Execution/Topology"| R2
    R1 -->|"Execution/State"| R3
    R5 -->|"Execution:<br/>seq → parallel"| R4
    R1 -->|"Topology:<br/>single → manager"| R5
```

## The evidence: same question, several architectures

Run every recipe against the same question and score each answer with OfficeQA's own reward
function:

```bash
uv run python evals/run_evals.py
```

Here's a committed run over the recipes' evaluation questions — the full artifact, with
per-question detail, lives in [`evals/results/latest.md`](evals/results/latest.md):

| Recipe | Questions | Accuracy | Avg model calls | Avg tokens |
|---|---|---|---|---|
| 00 · Closed-book baseline | 4 | 0.50 | 1.0 | 425 |
| 01 · Single document agent | 4 | 0.50 | 10.0 | 181,587 |
| 02 · Routed workflow | 4 | 0.50 | 6.5 | 33,030 |
| 03 · Planner–executor | 4 | 0.50 | 6.0 | 16,461 |
| 04 · Parallel investigation | 3 | 0.33 | 11.7 | 158,660 |
| 05 · Manager–worker | 4 | 0.50 | 17.8 | 67,741 |

Read this slowly, because it is *not* the tidy story you'd expect. These are genuinely hard
questions, and every architecture lands around 0.50 — document access is *necessary* (the
closed-book baseline only scores where the model already knew the figure), but on multi-step
numeric questions it is not *sufficient*: the agents still misread tables and botch arithmetic.

Now look at the cost columns. The manager–worker system averages **17.8 model calls** — one
question took 26 — to reach the same 0.50 as the planner–executor's **6 calls and ~16k tokens**.
The fancy topologies cost 3–18× more here and buy no accuracy. Beautiful diagrams, far more
machinery, same score.

I can't emphasize this caveat enough: these are *real model runs*, so exact cells shift between
runs — regenerate the file with `--out` and the numbers move. The **pattern** is the durable
lesson, not any single number: document access is the lever that matters, extra machinery is not
free, and it is not automatically better. Pick the simplest architecture that clears your
reliability bar, and make every fancier recipe earn its price. Do not be a hero.

## Is this cheating? (No — and here's exactly what's real)

Fair question, because a lot of "agent" demos quietly fake the hard part. Here nothing is faked:

- **The data is real.** 697 actual Treasury Bulletin PDFs (1939–2025), parsed to text. The agent
  reads the real tables.
- **The model is real.** Every recipe calls a real model (Databricks, via the Unity AI Gateway).
  There is no scripted/offline fake path — a wrong answer is a real wrong answer.
- **The grading is real.** Answers are scored by OfficeQA's own `reward.py`, vendored unchanged.

The one simplification, and I want to be upfront about it: **oracle retrieval.** Each question
ships the exact documents that contain its answer, and we hand those to the agent. That's
deliberate — this cookbook teaches agent *architecture*, so we isolate it from the separate
retrieval problem. A production system would add a real search-the-whole-corpus tool. That's a
Feedback/Execution concern, and it doesn't change any recipe's topology.

## Running it

Everything calls a real model over real (gated) data, so you need two credentials in `.env`:

```bash
cp .env.example .env
# DATABRICKS_HOST + DATABRICKS_TOKEN  → the model, via the Unity AI Gateway
# FACETS_MODEL                        → e.g. system.ai.claude-sonnet-5
# HF_TOKEN                            → a Hugging Face token with access to the gated
#                                       databricks/officeqa dataset (accept its terms first)
uv run python recipes/01_single_tool_agent/app.py --uid UID0056
```

The recipe code doesn't change based on which model you point at — the `ModelProvider` behind it
does. That seam is the point.

## What's in the repo

```text
src/facets/           The runtime, framework-neutral: the Agent loop, the Tool and ModelProvider
                      protocols (FakeModel for unit tests, DatabricksModel for real runs),
                      TaskState, ApprovalPolicy, Trace, Evaluator, the typed FACETS manifest.
src/facets/officeqa/  The scenario: the OfficeQA dataset client, the document tools, and the
                      official reward.py wired up as a FACETS scorer.
recipes/              Six runnable recipes (00–05). Each changes one FACETS axis from the last.
evals/                The comparison harness that produced the table above.
docs/                 The MkDocs site.
schema/               The JSON Schema for facets.yaml.
```

Every recipe carries a `README.md`, a schema-validated `facets.yaml` (its architecture written
down as data), a Mermaid `diagram.mmd`, a runnable `app.py`, and an `eval.yaml`.

## Toy code vs. production

The recipes are deliberately the smallest version that still runs the real algorithm. A
production system keeps the same architecture but adds the plumbing a tutorial skips. It's worth
separating two kinds of "adds," because they're not the same thing:

- **Same behavior, better numbers:** batching, caching, concurrent model calls, a faster provider.
  Algorithmically identical, dramatically more efficient.
- **Different guarantees:** real retrieval over the full corpus; durable task state that survives a
  crash (recipe 03 makes the plan an explicit artifact — step one toward this); authority enforced
  in *code* so a prompt can't approve its own dangerous action; retries, idempotency, audit trails,
  real tracing. These change what the system *promises*, not just how fast it is.

What ships today is the mechanism, not the hardening.

## The mental model to keep

- An agent architecture is **six independent decisions** (FACETS), not a single label like
  "multi-agent."
- Hold five fixed, change one, and the effect shows up in the trace. Measurable, every time.
- The simplest architecture that clears your reliability bar is usually the right one. Autonomy
  and extra agents have to earn their keep.

```text
Single LLM call → Single tool-using agent → Workflow (router/planner) → Multi-agent system
```

Move one step to the right only when the step to its left genuinely isn't enough. That's it.

## Where to go next

Read [`docs/facets-framework.md`](docs/facets-framework.md) for the six axes in full, then open
whichever recipe changes the axis you care about — routing, planning, parallelism, or delegation.
To read the docs as a site:

```bash
uv sync --extra docs
uv run mkdocs serve      # http://127.0.0.1:8000
```

## Status

The framework, the runtime, the OfficeQA scenario, Recipes 00–05, the comparison harness, and the
docs. Still on the roadmap: handoffs, maker–checker, durable execution, approval-gated actions, a
composed production system, and a deeper Databricks/MLflow track. See
[`docs/recipes/index.md`](docs/recipes/index.md#roadmap).

## Credits & license

This repo is [Apache 2.0](LICENSE). It builds on the
[OfficeQA benchmark](https://github.com/databricks/officeqa) by Databricks: `reward.py` is
vendored under Apache-2.0 (see [NOTICE](NOTICE)), and the dataset (CC-BY-SA-4.0) is downloaded at
runtime, not redistributed here.
