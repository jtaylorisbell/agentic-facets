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

A representative single-question run (`UID0121`: "how many investor-type categories held more than
\$200 million as of the January 1980 ownership survey?", ground truth **2**):

| Recipe | Answer | Correct? | Model calls |
|---|---|---|---|
| 00 · Closed-book baseline | 6 | ✗ | 1 |
| 01 · Single document agent | 2 | ✓ | 5 |
| 02 · Routed workflow | 2 | ✓ | 6 |
| 05 · Manager–worker | 6 | ✗ | 10 |

Read this carefully, because it is the whole point:

- **The closed-book baseline is wrong.** No model has this 1980 table memorized. That failure is
  what justifies giving the model document tools at all.
- **Document access fixes it.** The single agent reads the table and gets it right, for a handful
  of model calls.
- **More machinery is not more capability.** The manager–worker system spent *more* model calls
  and still got it wrong — the coordination overhead bought nothing here. Multi-agent earns its
  keep when one context genuinely can't hold the problem, not by default.

!!! note "Results vary"
    These are real model runs, so exact answers and counts shift between runs. The **pattern** —
    baseline fails, document access helps, extra agents don't automatically help — is the durable
    lesson, not any single cell.

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
