# Recipe 03 — Planner–executor

> **FACETS:** `F=closed-loop  A=advisory  C=model-directed  E=planner-executor  T=single-agent  S=durable-task`

## Problem

The same OfficeQA question. This time we make the **plan an explicit artifact** — the system
decides which documents to read and what to compute up front, executes those steps, then inspects
the results and re-plans if the evidence is insufficient.

## What changed?

Relative to [Recipe 01](../01_single_tool_agent/):

```diff
 Execution:
-  reactive tool loop   # next tool chosen implicitly, one step at a time
+  plan-then-execute    # a structured plan is emitted, executed, then revised

 State:
-  message history      # the "plan" lives implicitly in the conversation
+  explicit task plan   # TaskState.plan — a first-class, persisted, inspectable artifact
```

Recipe 01 already used a planner–executor *shape* implicitly. The point here is to make the plan
**explicit and durable**: a structured list of steps you can inspect, checkpoint, and resume —
the foundation for durable execution ([Recipe 08](../), later).

## Architecture

```mermaid
flowchart TB
    Q([Treasury Bulletin question]) --> P{{Planner: emit JSON plan}}
    P --> E[Execute steps via document tools]
    E --> Store[(Task state:<br/>plan + results)]
    Store --> I{Enough evidence?}
    I -->|no, re-plan| P
    I -->|yes| S{{Synthesize answer}}
    S --> Out([Answer + FINAL_ANSWER])
```

## Minimal implementation

```bash
uv run python recipes/03_planner_executor/app.py
uv run python recipes/03_planner_executor/app.py --uid UID0056
```

- **Planner** (`_plan`): a model call returning JSON — `{"steps": [...], "done": bool}` — given
  the goal and the results gathered so far.
- **Executor** (`_execute_step`): *code* dispatches each planned step to a document tool and
  records the result on `TaskState`.
- The loop re-plans until the planner says `done` (bounded by `MAX_REPLANS`).

## Walkthrough

1. **Plan:** the planner lists the source documents, then plans a search for the relevant table.
2. **Execute:** each step runs; results are persisted to `TaskState.plan` and `artifacts`, with
   checkpoints recorded around every step.
3. **Inspect / re-plan:** seeing the table, the planner adds `compute` steps for the arithmetic.
4. **Done → synthesize:** the planner returns `done`, and a final call writes the answer with the
   `<FINAL_ANSWER>` tag.

## Failure lab

- **Over-planning:** a planner that front-loads every read wastes calls. The prompt discourages
  this ("request only the steps you still need"), and the re-plan loop rewards gathering
  incrementally.
- **Malformed plan JSON:** `_parse_plan` tolerates prose and code fences and degrades to
  `done=true` rather than crashing.
- **Non-termination:** `MAX_REPLANS` bounds the loop; exhausting it yields
  `stopped_reason="max_replans"`. A planner that returns no steps but isn't done stops with
  `no_progress`.

## Evaluation

Similar correctness to the other agent recipes, with model calls split between **planning,
per-step execution, and a final synthesis**. The payoff isn't fewer tokens — it's a plan you can
inspect and resume. Run `evals/run_evals.py`.

## When to use it

- The path can't be fully known in advance, but you want the reasoning about *what to do* made
  explicit and separable from *doing it*.
- You need resumability — a durable plan is the precondition for durable execution.

## When *not* to use it

- The question is short and the implicit loop of [Recipe 01](../01_single_tool_agent/) is enough —
  an explicit plan adds ceremony you may not need.
