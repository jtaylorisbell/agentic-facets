# Recipe 00 — Closed-book baseline

> **FACETS:** `F=open-loop  A=advisory  C=code-directed  E=sequential  T=none  S=request-local`

## Problem

Answer a hard, document-grounded question from the OfficeQA benchmark — a real corpus of U.S.
Treasury Bulletins. Example: *"How many investor-type categories held more than $200 million as
of the January 1980 ownership survey?"* The answer is a specific value buried in a specific
table.

This recipe is the **dumbest thing that could possibly work**: ask the model directly, one call,
no tools, no documents. It is the control every other recipe is measured against.

## What changed?

Nothing yet — this is the starting point.

## Architecture

```mermaid
flowchart LR
    Q([Treasury Bulletin question]) --> M{{Model: answer from memory}}
    M --> A([Answer + FINAL_ANSWER])
```

**Control** is `code-directed` in the trivial sense: code makes exactly one model call and
returns the text. The model has no way to consult a document.

## Minimal implementation

See [`app.py`](./app.py) — one `model.complete(...)` call with the question, no tools.

```bash
uv run python recipes/00_closed_book_baseline/app.py
uv run python recipes/00_closed_book_baseline/app.py --uid UID0030
```

## Walkthrough

1. The question goes to the model with an instruction to answer from memory and wrap the answer
   in `<FINAL_ANSWER>…</FINAL_ANSWER>`.
2. The model answers in one shot.
3. The official OfficeQA `reward.py` scorer compares the answer to ground truth.

## Failure lab

- **It usually gets it wrong.** These answers live in specific 1940s–2000s Treasury Bulletin
  tables that no model has memorized. Watch it produce a confident, plausible, *wrong* number.
- **That failure is the whole point.** It is the concrete motivation for giving the model
  document access in [Recipe 01](../01_single_tool_agent/). Autonomy is earned; so is a retrieval
  tool — you add it because the baseline demonstrably can't answer without it.

## Evaluation

Expect **low answer correctness** at the lowest possible cost (one model call). That is the bar
every richer architecture has to beat. Run `evals/run_evals.py` to see it next to the others.

## When to use it

- The model plausibly already knows the answer (general knowledge, not private/obscure data).
- You want a cost floor and a correctness floor to compare against.

## When *not* to use it

- The answer lives in documents the model hasn't memorized → give it tools
  ([Recipe 01](../01_single_tool_agent/)).
