# Design note: a second scenario (GAIA)

**Status:** design, not built. This note scopes adding [GAIA](https://huggingface.co/datasets/gaia-benchmark/GAIA)
as a *second* scenario alongside OfficeQA, and records what the real dataset actually contains — so
the decision to build (or not) is made on facts, not on GAIA's reputation.

## Why a second scenario at all

The OfficeQA grid answered "is architecture as strong a lever as the model?" cleanly. But it did so
on a **homogeneous** task: every question is "read one or two Treasury tables, do arithmetic, emit a
number." That shape genuinely exercises **Control** (00→01, giving the model documents) and partly
**Execution** (03, the planner). It barely exercises the rest:

- **Routing (02)** earns its keep when requests are *heterogeneous* and need classifying. OfficeQA is
  homogeneous — every question routes to the same "go read the table" path, so the router has nothing
  real to decide.
- **Delegation (05)** is for tasks that *decompose* into distinct specialist sub-problems. A
  single-table lookup doesn't decompose. Tellingly, 05 scores highest on OfficeQA **and** burns the
  most tokens — its win is plausibly "did more work / more implicit self-checking," not "delegation
  was the right topology." That's a confound.
- **Parallelism (04)** only bites on the multi-document subset, and even there fan-out buys latency,
  not accuracy.

So the cross-recipe numbers for 02/04/05 on OfficeQA are partly driven by compute budget, not by the
FACETS axis each recipe is meant to isolate. A heterogeneous, multi-step task would give those axes
something real to bite on. GAIA is that task.

## Correction to the earlier verbal spike

An earlier back-of-envelope estimate claimed GAIA could be split into "Tier A (file-attachment,
reproducible) ≈ 90% of the teaching value" and "Tier B (open web), deferrable." **Loading the real
validation metadata falsifies that.** GAIA is fundamentally a *web-agent* benchmark; the open web is
the substrate, not an optional tier.

Measured on the public **validation** split (165 questions, `2023/validation/metadata.parquet`):

| Slice | Count | Share |
|---|---|---|
| **No attachment — open-web questions** | **127** | **77%** |
| Need a web browser / search engine (per annotator "Tools") | 122 | 73% |
| Ship a file attachment (any kind) | 38 | 23% |
| — text/table files (xlsx, csv, txt, docx, pdf, py) | 21 | 13% |
| — of those, **genuinely file-only** (annotator lists no web) | **13** | **8%** |
| — image files (png, jpg) | 10 | 6% |
| — audio files (mp3) | 3 | 2% |
| — archives / other (zip, pdb, pptx) | 4 | 2% |

The self-contained, no-web, no-vision, no-audio slice is **13 questions**. Building "Tier A first,
defer the web tool" would deliver ~8% of the benchmark, not 90% of the value. **If we add GAIA, we
are signing up for a real web-search/browse tool** — that is the whole point of the dataset.

## What GAIA actually is (verified against the repo)

- **Validation split:** Level 1 = 53, Level 2 = 86, Level 3 = 26 → **165** questions, with public
  answers. The **test** split (Level 1 = 93, L2 = 159, L3 = 49) has private answers (leaderboard
  only), so we'd develop against validation.
- **Record schema** (`metadata.parquet`): `task_id`, `Question`, `Level`, `Final answer`,
  `file_name`, `file_path`, and `Annotator Metadata` — a struct with `Steps`, `Number of steps`,
  `How long did this take?`, `Tools`, `Number of tools`. That last pair is a gift: it tells us how
  many tools a question was *designed* to need, so we can bucket by intended complexity.
- **Complexity climbs with level** (validation): avg tools/question L1 = 1.6, L2 = 2.5, L3 = 3.4
  (max 6). Attachments are the minority at every level (no-file: L1 42/53, L2 66/86, L3 19/26).
- **Metadata is parquet, not CSV.** The stdlib can't read it. OfficeQA's dataset client reads CSV
  with `csv` from the standard library specifically to avoid a pandas/pyarrow dependency (the repo is
  deliberately lean — it avoids even `python-dotenv`). GAIA would force `pyarrow` (or `pandas`) into
  the runtime, or a one-time convert-to-JSONL step. This is a real, if small, cost.
- **Gated, no-reshare**, same as OfficeQA — the existing `HF_TOKEN` already has access, and we'd
  store only `task_id`s in the repo, never question text.

## Scoring (verified from the leaderboard `scorer.py`)

Exact match after normalization, close to OfficeQA's contract but stricter:

- **Numbers:** strip `$ % ,` then `float()`, compared with **exact `==`** — *no* tolerance (OfficeQA's
  scorer allows 1%). We'd reimplement GAIA's ~40-line normalizer rather than vendor it (avoids a
  license question, and it's small).
- **Strings:** strip all whitespace, lowercase, strip punctuation, compare.
- **Lists:** split on `[,;]`, element-wise with the rules above; **lengths must match**.
- **Known scorer bug to sidestep:** `is_float()` on the ground truth does *not* strip commas, so a GT
  like `1,500` is treated as a *list* `[1, 500]` and a correct `1500` mis-scores. If we reimplement,
  we fix this (strip separators before the number/list decision) and note the divergence from the
  official scorer.

The answer convention is `FINAL ANSWER: <x>`; our recipes already emit `<FINAL_ANSWER>…</FINAL_ANSWER>`
— we extract from our tag, then feed the value to GAIA's normalizer, so the recipe contract is
unchanged.

## How it maps onto the recipes (the payoff)

GAIA's heterogeneity is what finally makes the weak-fit recipes honest tests of their axis:

| Axis | On OfficeQA | On GAIA |
|---|---|---|
| **Control** (00→01) | ✅ clean | ✅ clean |
| **Execution / planner** (03) | ⚠️ partial | ✅ multi-step chains genuinely need a plan |
| **Topology / routing** (02) | ❌ homogeneous → nothing to route | ✅ "spreadsheet task vs. web-browse task?" is real classification |
| **Topology / delegation** (05) | ❌ doesn't decompose | ✅ L3 tasks decompose into distinct sub-problems |
| **Execution / parallel** (04) | ⚠️ only 2-doc subset | ✅ independent sub-questions to fan out |
| **Feedback / Authority** | ❌ read-only, no verification hook | ✅ verifiable intermediate results; browsing = real actions to gate |

A natural new chart: **accuracy vs. `Number of tools`, per architecture.** If the fancy topologies
pull ahead exactly where task complexity is high (and stay flat where it's low), that's the strongest
rebuttal to "05 only won on OfficeQA because it burned more compute."

Suggested level→recipe emphasis: **L1** → 01 (the clean control); **L2** → 02 routing, 03 planning;
**L3** → 04 parallel, 05 delegation.

## The module, mirroring `src/facets/officeqa/`

The OfficeQA package is a clean three-part contract, and GAIA maps onto it almost 1:1. The recipe
entrypoint `run(question, dataset, *, model) -> AgentResult` stays **unchanged**.

| OfficeQA | GAIA equivalent | Change |
|---|---|---|
| `OfficeQADataset(subset)` → `Question(uid, question, answer, source_files, …)` | `GAIADataset(split="validation")` → `GAIAQuestion(task_id, question, answer, level, file_name, num_tools)` | reads `metadata.parquet`; downloads the one attachment per question |
| `build_document_tools(ds, source_files)` | `build_gaia_tools(question)` | **the hard part — the web tool + a multi-format file tool** |
| `answer_correctness_scorer(tolerance=0.01)` | `gaia_correctness_scorer()` | reimplement GAIA's exact-match normalizer (no tolerance; fix the comma bug) |
| `FINAL_ANSWER_INSTRUCTION` | reuse the same tag, extract, feed to GAIA's normalizer | none |

**Tools are where the cost lives.** GAIA needs, at minimum:

1. **`web_search` + `fetch_page`** — the 73% majority. Needs a search dependency/API key
   (Tavily/Brave/DuckDuckGo) and accepts that results **drift**: a committed answer artifact won't
   reproduce months later, which breaks the repo's current reproducibility promise. This is the big
   one, and it's unavoidable.
2. **A multi-format file tool** — `read_file` / `inspect_spreadsheet` (openpyxl/csv) / `read_pdf` /
   `describe_image` (needs a vision-capable model — Claude on the gateway qualifies) / `transcribe`
   (audio — the 3 mp3s; likely out of scope for a first cut). `compute` is reused verbatim.

## The one architectural decision: the scenario seam

Recipes currently `import` OfficeQA directly (`from facets.officeqa import …`) and hard-code
Treasury-specific system prompts. To run *both* scenarios you need a small **scenario seam**:

- **(a) A `Scenario` protocol** — `dataset`, `build_tools(question)`, `scorer`,
  `final_answer_instruction`, `system_prompt`. Recipes take a `scenario` parameter, so one recipe body
  runs on either benchmark. Clean, but touches all six recipes and the harness (which already threads
  `model` per cell — adding `scenario` is symmetric). **Recommended.**
- **(b) A parallel `recipes_gaia/`** — zero refactor, honors "read each recipe top-to-bottom in
  isolation," but duplicates ~200 lines and lets the two drift.

Recommend **(a)**: it's the change that makes the cookbook's "same architecture, different task"
thesis *executable* rather than asserted.

## Effort & open items

- **Scenario seam (a):** ~half a day; touches all recipes + `_common.py` + the harness.
- **GAIA dataset client + scorer:** ~half a day. Scorer is ~40 lines; the parquet read forces a
  `pyarrow` dependency (or a convert step) — decide which.
- **Web tool (search + fetch):** ~1 day + **ongoing flakiness and non-reproducibility**. This is the
  crux; it's what the OfficeQA "oracle retrieval" simplification was specifically avoiding.
- **Multi-format file tool (Tier A):** ~half a day for spreadsheet/pdf/text; vision via the model;
  audio deferred.
- **Open items:** (1) search-provider choice + key management (OAuth rule doesn't apply — it's a
  third-party API; store its key like `HF_TOKEN`); (2) how to keep a committed results artifact
  meaningful when the web drifts (pin a date? mark GAIA results "point-in-time, not reproducible"?);
  (3) reimplement vs. vendor the scorer (lean toward reimplement).

## Recommendation

Add GAIA as a **second scenario, not a replacement.** Keep OfficeQA as the *clean-room* — its
homogeneity and oracle retrieval are what make the 00→01 result crisp and reproducible. Add GAIA as
the *wild*, where routing/delegation/parallelism (and later, real retrieval + approval-gated browsing)
earn their keep. The pedagogy becomes: *here's a task where more machinery is overkill (OfficeQA), and
here's one where it's essential (GAIA) — match the architecture to the task.*

But go in clear-eyed: GAIA means a **real web tool, multimodality, and a genuine dent in
reproducibility.** That's a scenario build, not a tweak — and it's worth doing precisely because it
tests what OfficeQA can't.
