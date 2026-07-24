# Recipe 00 · Closed-book baseline

> **FACETS:** `F=open-loop · A=advisory · C=code-directed · E=sequential · T=none · S=request-local`

The control every other recipe is measured against — the dumbest thing that could possibly work.
It takes a hard, document-grounded question from the OfficeQA benchmark (a real corpus of U.S.
Treasury Bulletins) and asks the model directly: one call, no tools, no documents. Code makes
exactly one `model.complete(...)` call and returns the text; the model has no way to consult the
document the answer lives in.

```mermaid
flowchart LR
    Q([Treasury Bulletin question]) --> M{{Model: answer from memory}}
    M --> A([Answer + FINAL_ANSWER])
```

## Run it

```bash
uv run python recipes/00_closed_book_baseline/app.py
uv run python recipes/00_closed_book_baseline/app.py --uid UID0030
```

## What it teaches

- **It usually gets it wrong.** These answers live in specific 1940s–2000s Treasury Bulletin
  tables no model has memorized — watch it produce a confident, plausible, *wrong* number.
- **That failure is the whole point.** It's the concrete motivation for giving the model document
  access in [Recipe 01](01-single-tool-agent.md). A retrieval tool is *earned*: you add it because
  the baseline demonstrably can't answer without it.
- **It's a floor, not a target.** Expect low answer correctness at the lowest possible cost (one
  model call). That's the bar every richer architecture has to beat — see [Evaluation](../evaluation.md).

## Source

[`recipes/00_closed_book_baseline/`](https://github.com/jtaylorisbell/agentic-facets/tree/main/recipes/00_closed_book_baseline)
