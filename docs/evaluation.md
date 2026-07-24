# Evaluation

FACETS only earns its keep if the differences between architectures are **measured**, not
asserted. The cookbook's thesis — *"we built the same agent several ways; here's what changed"* —
is backed by a comparison table over one shared incident.

## Run it

```bash
uv run python evals/run_evals.py
```

The harness discovers every recipe that ships an `eval.yaml`, runs its `run()` entrypoint with
the offline scripted model, scores the result, and prints one row per recipe. Because the offline
runs are deterministic, it doubles as a regression test (and exits non-zero if any recipe fails
its task, so it works as a CI gate).

## The result

| Recipe | Task success | Tool correctness | Model calls | Total tokens | Steps |
|---|---|---|---|---|---|
| 00 · Deterministic baseline | 1.00 | 1.00 | **0** | 0 | 0 |
| 01 · Single tool agent | 1.00 | 1.00 | **5** | ~1.5k | 5 |
| 02 · Routed workflow | 1.00 | 1.00 | **5** | ~1.2k | 4 |
| 03 · Planner–executor | 1.00 | 1.00 | **4** | ~1.9k | 4 |
| 04 · Parallel investigation | 1.00 | 1.00 | **9** | ~1.1k | 5 |
| 05 · Manager–worker | 1.00 | 1.00 | **13** | ~1.9k | 5 |

Every architecture solves the incident. What differs is *how* — one classification call plus a
scoped specialist (02), a plan/execute/replan loop (03), four concurrent branches plus a
synthesis (04), or sequential delegation to a manager's workers (05). **That contrast is the
lesson:** pick the lowest rung on the
[escalation ladder](choosing-a-pattern.md#the-escalation-ladder) that clears your reliability bar
— the fanciest architecture that works is rarely the one you want.

!!! note "Reading the numbers"
    Model-call count isn't a quality ranking — it reflects each architecture's *shape*. The
    planner–executor looks cheap here because the offline script converges fast; parallel
    investigation trades tokens for wall-clock latency (invisible in a deterministic run). The
    point is that the axes have *costs*, and the table makes them visible.

*(Token counts use a deterministic offline estimate; absolute numbers shift under a live model,
but the ordering is the point.)*

## Metrics

The framework calls for measuring:

- **Task success** — did it reach the correct outcome? (Here: did it name the root cause and
  finish rather than truncate?)
- **Tool-use correctness** — did it call the tools the task needed?
- **Model-call count / token cost / latency** — what did the architecture cost?
- Later, as recipes add authority and durability: **unsupported claims, policy violations, and
  human-intervention rate**.

## Scorers

Scorers are plain callables (`(case, result) -> Score`), so scenario-specific ones compose with
the built-ins. The two shipped scorers live in
[`facets.evaluation`](https://github.com/jtaylorisbell/agentic-facets/blob/main/src/facets/evaluation.py):

```python
from facets.evaluation import Evaluator, task_success_scorer, tool_correctness_scorer

evaluator = Evaluator([task_success_scorer(), tool_correctness_scorer()])
report = evaluator.evaluate(case, recipe="01_single_tool_agent", result=result)
print(report.as_row())
```

Every run carries a [`Trace`](https://github.com/jtaylorisbell/agentic-facets/blob/main/src/facets/tracing.py)
with rolled-up model calls, tokens, latency, and the ordered list of tool calls — which is what
the scorers and the table read from.
