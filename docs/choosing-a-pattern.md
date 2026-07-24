# Choosing a Pattern

Complete a **FACETS design card** before writing code. Answer these in order; each answer sets
one axis and narrows the next.

```text
Does the path need to change at runtime?
  No  → Deterministic workflow            (Control: code-directed)
  Yes → Model-directed control            (Control: model-directed)

Can one model retain enough context and expertise?
  Yes → Single agent                      (Topology: single-agent)
  No  → Consider specialists              (Topology: manager-worker / handoff)

Are subtasks independent?
  Yes → Parallel execution                (Execution: parallel)
  No  → Sequential or planner–executor     (Execution: sequential / planner-executor)

Can success be checked deterministically?
  Yes → Deterministic feedback            (Feedback: deterministic-validation)
  No  → Combine environmental, model, and human review   (Feedback: hybrid)

Must work survive interruptions?
  Yes → Durable task state                (State: durable-task / persistent)

Can the system make consequential changes?
  Yes → Explicit authority + approval policy   (Authority: approval-gated / bounded)
```

## The escalation ladder

Autonomy is **earned**. Only move down a rung when the rung above genuinely can't do the job:

```text
Single LLM call
    ↓ only when insufficient
Deterministic workflow           →  Recipe 00
    ↓ only when runtime decisions are necessary
Single tool-using agent          →  Recipe 01
    ↓ only when context or specialization requires it
Multi-agent system               →  Recipe 05
```

## Worked example: the incident investigator

The cookbook applies the card to one problem — *a data pipeline failed; find the root cause* —
and moves exactly one axis at a time:

| Recipe | Axis changed | Resulting profile (abbrev.) |
|---|---|---|
| [00 Deterministic baseline](recipes/00-deterministic-baseline.md) | — (start) | `C=code-directed · T=none` |
| [01 Single tool agent](recipes/01-single-tool-agent.md) | **Control** → model-directed | `C=model-directed · T=single-agent` |
| [05 Manager–worker](recipes/05-manager-worker.md) | **Topology** → manager-worker | `C=model-directed · T=manager-worker` |

The [evaluation](evaluation.md) shows all three solve the incident — at escalating cost. That's
the lesson: pick the lowest rung that clears your reliability bar, not the fanciest.

## Common traps

- **Reaching for multi-agent by default.** More agents add coordination overhead and token cost
  without automatically improving results. Prove a single agent *can't* do it first.
- **Treating human-in-the-loop as a single design.** It's a placement decision on the
  [Authority](facets-framework.md#a-authority) axis — decide *where* the human sits.
- **Confusing reflection with verification.** A critic model *reasoning* that an answer looks
  right is not the same as *checking it against the environment*. See
  [Feedback](facets-framework.md#f-feedback).
- **Letting the prompt be the authorization boundary.** Enforce Authority in code.
