# Evaluation

FACETS only earns its keep if the differences between architectures are **measured**, not
asserted. The cookbook's thesis — *"we built the same agent several ways; here's what changed"* —
is backed by running the **same OfficeQA questions** through every recipe and scoring the answers
with OfficeQA's own reward function.

Because the model and data are real, results vary run to run, and a wrong answer is a real wrong
answer — not a scripted one.

## Run it

```bash
uv run python evals/run_evals.py
uv run python evals/run_evals.py --uids UID0030,UID0121      # override the question set
uv run python evals/run_evals.py --recipes 00_closed_book_baseline,01_single_tool_agent
```

The harness discovers every recipe that ships an `eval.yaml`, runs its `run(question, dataset,
model=...)` entrypoint on each listed question with a real Databricks model, scores each answer
with [`reward.py`](https://github.com/databricks/officeqa) (exact + numeric-tolerance matching),
and prints per-recipe **answer accuracy** and **average cost**.

## What you see

Here is a committed, reproducible run over the recipes' evaluation questions (the full artifact,
including per-question detail, is in
[`evals/results/latest.md`](https://github.com/jtaylorisbell/agentic-facets/blob/main/evals/results/latest.md)
and `latest.json`). Model: `system.ai.claude-sonnet-5`.

| Recipe | Questions | Answer accuracy | Avg model calls | Avg tokens |
|---|---|---|---|---|
| 00 · Closed-book baseline | 4 | 0.50 | 1.0 | 425 |
| 01 · Single document agent | 4 | 0.50 | 10.0 | 181,587 |
| 02 · Routed workflow | 4 | 0.50 | 6.5 | 33,030 |
| 03 · Planner–executor | 4 | 0.50 | 6.0 | 16,461 |
| 04 · Parallel investigation | 3 | 0.33 | 11.7 | 158,660 |
| 05 · Manager–worker | 4 | 0.50 | 17.8 | 67,741 |

Read this carefully, because it is the whole point — and it is *not* the tidy story you might
expect:

- **These are genuinely hard questions.** Every architecture lands around 0.50. Document access
  is necessary (the closed-book baseline only scores where the model already happened to know the
  figure), but on multi-step numeric questions it is not sufficient — the agents still misread
  tables and botch arithmetic.
- **The cost differences are enormous, and buy nothing here.** Manager–worker averages **17.8
  model calls** (one question took 26); parallel investigation burns **~159k tokens** per
  question; the planner–executor reaches the same 0.50 accuracy in **6 calls / ~16k tokens**. On
  this set, the fancy topologies cost 3–18× more for no accuracy gain.
- **The failure modes are real and visible** in the per-question detail: `max_steps`,
  `max_replans`, and a single agent that burned 494k tokens on one question and still got it
  wrong.

!!! note "Results vary"
    These are real model runs, so exact answers and counts shift between runs — regenerate the
    artifact with `--out` and the cells will move. The **pattern** is the durable lesson, not any
    single number: document access is necessary but not sufficient, and extra machinery is not
    free and not automatically better.

## Reproduce it

```bash
uv run python evals/run_evals.py --out          # writes evals/results/latest.{json,md}
uv run python evals/run_evals.py --out --concurrency 3   # gentler on the gateway's rate limit
```

## Metrics

- **Answer accuracy** — did the final `<FINAL_ANSWER>` match ground truth (exact, or within
  numeric tolerance) per OfficeQA's `reward.py`?
- **Model-call count / token cost** — what did the architecture cost to get there?
- Later, as recipes add authority and durability: **unsupported claims, policy violations, and
  human-intervention rate**.

## Scorers

The OfficeQA scorer wraps the official reward function as a FACETS `Scorer`:

```python
from facets.officeqa import answer_correctness_scorer
from facets.evaluation import EvalCase

scorer = answer_correctness_scorer(tolerance=0.01)
case = EvalCase(id=q.uid, goal=q.question, metadata={"answer": q.answer})
score = scorer(case, result)   # 1.0 if the answer matches ground truth, else 0.0
```

The contract: the recipe's answer must contain the value inside `<FINAL_ANSWER>…</FINAL_ANSWER>`.
Every run also carries a [`Trace`](https://github.com/jtaylorisbell/agentic-facets/blob/main/src/facets/tracing.py)
with rolled-up model calls, tokens, and the ordered list of tool calls, which is what the cost
columns read from.
