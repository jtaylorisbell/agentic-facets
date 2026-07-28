# Evaluation

FACETS only earns its keep if the differences between architectures are **measured**, not
asserted. The cookbook's thesis — *is the agent architecture as strong a lever as the model behind
it?* — is a claim about two effects and their relative size, so the only honest way to settle it
is a **grid**: run the **same OfficeQA questions** through every recipe (the architecture axis)
*and* every model (the model axis), then compare how far each lever moves accuracy.

Because the models and data are real, results vary run to run, and a wrong answer is a real wrong
answer — not a scripted one.

## Run it

```bash
uv run python evals/run_evals.py                              # one model (FACETS_MODEL), each eval.yaml
uv run python evals/run_evals.py --models A,B,C               # sweep the model axis — the grid
uv run python evals/run_evals.py --models A,B --uids UID0121  # one shared question, several models
uv run python evals/run_evals.py --recipes 00_closed_book_baseline,01_single_tool_agent
```

The harness discovers every recipe that ships an `eval.yaml`, runs its `run(question, dataset,
model=...)` entrypoint on each listed question with each real Databricks model, scores each answer
with [`reward.py`](https://github.com/databricks/officeqa) (exact + numeric-tolerance matching),
and prints the accuracy matrix, the cost matrix, and the two lifts that argue the thesis.

An infra failure (a rate limit the retries couldn't outlast, a dropped connection) is **not** a
wrong answer — accuracy is computed over successfully-scored runs only, and the error count is
surfaced so you can weigh each cell's reliability. That distinction matters: scoring a throttled
run as `0.0` silently biases the stronger, slower models downward.

## What you see

Here is a committed, reproducible run of the full grid — three Claude models (a capability ladder)
× six architectures × the shared question set. The full artifact, with per-question detail, is in
[`evals/results/latest.md`](https://github.com/jtaylorisbell/agentic-facets/blob/main/evals/results/latest.md)
and `latest.json`.

**Answer accuracy** (over successfully-scored runs; `n` in parentheses):

| Recipe | `haiku-4-5` | `sonnet-5` | `opus-5` |
|---|---|---|---|
| 00 · Closed-book baseline | 0.20 (10) | 0.30 (10) | 0.20 (10) |
| 01 · Single document agent | 0.38 (8) | 0.40 (10) | **0.71** (7) |
| 02 · Routed workflow | 0.25 (8) | 0.30 (10) | 0.50 (10) |
| 03 · Planner–executor | 0.20 (10) | 0.30 (10) | 0.50 (10) |
| 04 · Parallel investigation | 0.33 (3) | 0.25 (4) | 0.60 (5) |
| 05 · Manager–worker | 0.33 (9) | 0.60 (10) | **0.80** (10) |

**Cost** (average tokens per question):

| Recipe | `haiku-4-5` | `sonnet-5` | `opus-5` |
|---|---|---|---|
| 00 · Closed-book baseline | 383 | 435 | 972 |
| 01 · Single document agent | 225,116 | 147,028 | 112,909 |
| 02 · Routed workflow | 137,858 | 76,120 | 79,775 |
| 03 · Planner–executor | 10,509 | 15,435 | 19,871 |
| 04 · Parallel investigation | 194,329 | 334,896 | 164,421 |
| 05 · Manager–worker | 189,479 | 216,303 | 313,328 |

Read the grid down a column and across a row, because both directions carry the lesson:

- **Closed-book, every model is bad — and roughly equally bad** (0.20–0.30, a 0.10 spread). Nobody
  has an obscure 1980 Treasury Bulletin table memorized, so raw model choice barely matters when
  the model is flying blind. This is the honest control: *the model alone is not the lever.*
- **Architecture is the bigger lever, and it compounds with the model.** Hold a model fixed and
  give it the best architecture and accuracy climbs far more than upgrading the model ever did
  closed-book: `haiku` +0.17, `sonnet` +0.30, `opus` **+0.60** (0.20 → 0.80 with manager–worker).
  The two levers *multiply* — the biggest wins need a capable model **and** a real architecture,
  neither alone.
- **Weaker + architecture matches stronger + nothing.** On the shared questions, `haiku` with the
  single-document agent (0.38) **ties** `sonnet` answering closed-book (0.38). Give the small model
  the right wiring and it catches a bigger model that has none — the thesis, in one comparison.
- **…but architecture only pays off for a model capable enough to drive it.** The same
  manager–worker topology scores 0.33 for `haiku` and 0.80 for `opus`. Machinery is not magic; it
  is *leverage*, and leverage needs something to push on. (The pilot's `gpt-oss-20b` couldn't use
  document tools at all — 0.00 — a reminder that below some capability floor, more architecture
  makes things *worse*.)
- **The cost is the counterweight, and it is enormous.** `opus` + manager–worker buys 0.80 — at
  **313k tokens/question**, ~320× the closed-book baseline. The planner–executor reaches 0.50 for
  `opus` at **20k tokens**, 1/15th the cost. So "more machinery helps" and "pick the cheapest
  architecture that clears your bar" are *both* true: match the architecture to the model and to
  the reliability you actually need.

!!! note "Read the pattern, not the cell"
    These are real model runs on genuinely hard questions with a small `n` (10 lookup questions;
    fewer where rate limits cost us a cell — parallel investigation is the thinnest, `n`=3–5).
    Exact cells shift between runs; regenerate with `--out` and they move. The **durable signals**
    are the shape of the grid: the model alone is a weak lever, architecture is a strong one, the
    two compound, and the strongest cells cost 100–300× the simplest. Treat the numbers as
    directional evidence for those claims, not as a benchmark leaderboard.

## The two lifts, and the head-to-head

The harness reduces the grid to the numbers that actually argue the thesis, and prints them under
the matrix:

- **Model lift** — hold the architecture fixed (closed-book) and upgrade the LLM. Here: **+0.10**.
- **Architecture lift** — hold the model fixed and give it document tools (00 → 01). Here the
  weakest model gains **+0.17**, and the strongest gains **+0.51** on the same change.
- **Head-to-head** — weaker model + tools vs. stronger model, closed-book. Here they tie at
  **0.38**, so architecture is at least as strong a lever as the model.

The verdict the run prints: **architecture is the bigger lever** — and, read together with the
compounding above, the fuller truth is that architecture and model capability are complements, not
substitutes.

## Reproduce it

```bash
# The committed grid (three-model capability ladder):
uv run python evals/run_evals.py \
  --models system.ai.claude-haiku-4-5,system.ai.claude-sonnet-5,system.ai.claude-opus-5 \
  --out --concurrency 5

uv run python evals/run_evals.py --out          # single model (FACETS_MODEL), quick sanity run
```

Concurrency 5 keeps the gateway's rate limit mostly at bay; the retry logic (which honors the
server's `Retry-After` and backs off with jitter) plus the error-exclusion above make any residual
throttling safe rather than corrupting.

## Metrics

- **Answer accuracy** — did the final `<FINAL_ANSWER>` match ground truth (exact, or within
  numeric tolerance) per OfficeQA's `reward.py`? Computed over successfully-scored runs only.
- **Model-call count / token cost** — what did the architecture cost to get there? This is the
  counterweight to accuracy, and the grid shows it can differ by 100–300× across cells.
- **Infra errors** — runs that failed on rate limits or connection drops, reported per cell and
  excluded from accuracy (never scored as a wrong answer).
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
