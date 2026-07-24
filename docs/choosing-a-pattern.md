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
Single LLM call                  →  Recipe 00 (closed-book baseline)
    ↓ only when it needs to consult the environment
Single tool-using agent          →  Recipe 01
    ↓ only when runtime routing / planning helps
Workflow (router, planner)       →  Recipes 02, 03
    ↓ only when context or specialization requires it
Multi-agent system               →  Recipes 04, 05
```

## Worked example: the document-QA agent

The cookbook applies the card to one problem — *answer a hard, document-grounded OfficeQA
question* — and moves exactly one axis at a time:

| Recipe | Axis changed | Resulting profile (abbrev.) |
|---|---|---|
| [00 Closed-book baseline](recipes/00-closed-book-baseline.md) | — (start) | `C=code-directed · T=none` |
| [01 Single document agent](recipes/01-single-tool-agent.md) | **Control** → model-directed | `C=model-directed · T=single-agent` |
| [02 Routed workflow](recipes/02-routed-workflow.md) | **Execution** → router | `E=router · T=router-specialists` |
| [03 Planner–executor](recipes/03-planner-executor.md) | **State** → explicit plan | `E=planner-executor · S=durable-task` |
| [04 Parallel investigation](recipes/04-parallel-investigation.md) | **Execution** → parallel | `E=parallel · T=manager-worker` |
| [05 Manager–worker](recipes/05-manager-worker.md) | **Topology** → manager-worker | `C=model-directed · T=manager-worker` |

The [evaluation](evaluation.md) runs the same questions through each — the closed-book baseline
mostly fails, document access fixes that, and the fancier architectures don't automatically do
better. That's the lesson: pick the lowest rung that clears your reliability bar, not the
fanciest.

## Common traps

- **Reaching for multi-agent by default.** More agents add coordination overhead and token cost
  without automatically improving results. Prove a single agent *can't* do it first.
- **Treating human-in-the-loop as a single design.** It's a placement decision on the
  [Authority](facets-framework.md#a-authority) axis — decide *where* the human sits.
- **Confusing reflection with verification.** A critic model *reasoning* that an answer looks
  right is not the same as *checking it against the environment*. See
  [Feedback](facets-framework.md#f-feedback).
- **Letting the prompt be the authorization boundary.** Enforce Authority in code.
