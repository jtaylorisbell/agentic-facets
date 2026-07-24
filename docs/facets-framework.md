# The FACETS Framework

Six independent axes. A system is a *point* in this six-dimensional space, not a label.

## F — Feedback

**How does the system know whether it succeeded?**

- Open-loop generation (no check)
- Deterministic validation (schemas, row counts, types)
- Environmental verification (run the query, check the page changed, run the tests)
- Model-based critique (a critic model reviews the output)
- Human review
- Hybrid

A closed loop looks like:

```text
Decide → Act → Observe → Revise → Act again
```

Feedback is often more important than the number of agents. A single agent that *verifies its
work against the environment* beats a multi-agent system that never checks.

## A — Authority

**What may the system do independently?**

| Level | Example |
|---|---|
| Advisory | Recommend a fix; take no action |
| Drafting | Draft a ticket; a human sends it |
| Approval-gated | Restart a job only after human sign-off |
| Bounded autonomous | Issue refunds below a fixed threshold |
| Broad autonomous | Act freely within a domain |

Human-in-the-loop is **not one architecture** — it's a control-placement decision. Approval can
sit before planning, before specific tools, after execution, only for exceptions, or only below
a confidence threshold.

!!! warning "The one rule"
    **Prompts must never be the only authorization boundary for consequential actions.**
    Authority is enforced in code, outside the model. In this cookbook that's the
    [`ApprovalPolicy`](https://github.com/jtaylorisbell/agentic-facets/blob/main/src/facets/approvals.py):
    an action tool asks the policy — not the prompt — before it does anything, and fails safe
    (denied) if no policy is attached.

## C — Control

**Who chooses the next step?**

=== "Code-directed"

    The developer defines the execution graph. The model may decide *within* a step, but code
    decides what happens next.

    ```text
    Classify → Retrieve → Generate → Validate → Respond
    ```

=== "Model-directed"

    The model repeatedly decides what to do next — which tool, whether to gather more, when the
    task is done.

    ```text
    Observe → Decide → Act → Observe result → Decide again
    ```

A spectrum, from least to most autonomy:

```text
Prompt → Deterministic chain → LLM-routed workflow → Bounded tool-using agent → Open-ended agent
```

Most production systems should sit in the middle.

## E — Execution

**How does work progress?**

- **Sequential** — `A → B → C`; each stage depends on the last.
- **Parallel** — fan out independent subtasks, then aggregate.
- **Router** — classify the request, then branch.
- **Planner–executor** — `Goal → Plan → Execute → Inspect → Re-plan → Finish`; use when the path
  isn't known in advance.
- **Generator–critic** — `Generate → Critique → Revise → Validate`.
- **Handoff** — ownership moves as the problem evolves.
- **Event-driven / long-running** — `Event → Resume → Act → Checkpoint → Wait`.

## T — Topology

**How are the decision-makers organized?**

- **Single agent** — one context, several tools. *This should usually be the default.*
- **Router + specialists** — a router sends the request to a predefined specialist (often still
  a workflow, not a true multi-agent system).
- **Manager–worker** — a manager decomposes, delegates to workers, and synthesizes. Workers are
  intelligent tools; **the manager stays responsible.**
- **Handoff** — one agent owns the task at a time and *transfers* responsibility.
- **Peer / group chat** — several agents collaborate in a shared space (debate, negotiation),
  at the cost of coordination overhead.

!!! note "Manager–worker vs. handoff"
    The distinction is **ownership**. In manager–worker the manager remains responsible; in
    handoff, responsibility moves to the specialist.

## S — State

**What persists, and where is the source of truth?**

- Context-only (nothing survives the turn)
- Session (across turns of a conversation)
- Task state (goal, steps, artifacts, approvals, errors, checkpoints → resumability)
- Long-term semantic memory (reusable facts / preferences)
- Procedural memory (how to do recurring tasks)
- Environmental (the git repo, database, CRM, filesystem *is* the truth)

Every architecture should answer: *what does the agent remember, and where is the source of
truth?*

## A compact classification

```text
System = Feedback + Authority + Control + Execution + Topology + State
```

**Coding agent:** `F=compiler+tests · A=bounded file writes · C=model-directed ·
E=planner-executor · T=single-agent · S=repo + task state`

**Deep-research system:** `F=source comparison · A=read-only · C=model-directed ·
E=plan/fan-out/aggregate · T=manager + parallel workers · S=durable artifacts`

## The simple 2×2

For a quick discussion, start with two questions:

1. Is control **code-directed** or **model-directed**?
2. Is intelligence in **one** decision context or **several**?

| | Single context | Multiple contexts |
|---|---|---|
| **Code-directed** | LLM chain / workflow | Orchestrated specialist workflow |
| **Model-directed** | Tool-using agent | Multi-agent system |

Then overlay: sequential vs. parallel vs. iterative · stateless vs. durable · open-loop vs.
verified · read-only vs. action-taking · supervised vs. autonomous.

## The FACETS manifest

Every runnable system in this repo ships a `facets.yaml`, validated against
[`schema/facets.schema.json`](https://github.com/jtaylorisbell/agentic-facets/blob/main/schema/facets.schema.json).
This is what makes FACETS *adoptable* — the goal is for other teams to publish their own profile
and say "here is the FACETS profile of our architecture."

```yaml
name: single-tool-agent
feedback:
  mode: closed-loop
  mechanisms: [environmental-verification]
authority:
  level: advisory
control:
  mode: model-directed
  boundaries:
    max_steps: 8
execution:
  pattern: planner-executor
topology:
  pattern: single-agent
state:
  durability: request-local
  memory: context-only
```

Load and validate it in code:

```python
from facets.manifest import load_manifest

m = load_manifest("recipes/01_single_tool_agent/facets.yaml")
print(m.summary_line())
# F=closed-loop A=advisory C=model-directed E=planner-executor T=single-agent S=request-local
```
