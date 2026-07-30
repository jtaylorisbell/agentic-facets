"""GAIA dataset client.

GAIA (General AI Assistants) is a benchmark of real-world assistant tasks whose answers are
unambiguous but require multi-step tool use — web browsing, file handling, multimodality. See
https://huggingface.co/datasets/gaia-benchmark/GAIA (gated, no-reshare).

This mirrors :class:`~facets.officeqa.data.OfficeQADataset`:

1. Loads a split's question set from ``2023/{split}/metadata.parquet``.
2. Downloads and caches a question's single attachment on demand (``file_name`` → local path).

Two things differ from OfficeQA and are worth knowing:

* **Metadata is parquet, not CSV**, so — unlike OfficeQA, which reads CSV with the standard
  library — this needs ``pyarrow`` to read it. We import it lazily (as OfficeQA does with
  ``huggingface_hub``) and raise an actionable error if it is absent, so the rest of the package
  imports cleanly without the dependency.
* **GAIA is a web-agent benchmark**: only ~23% of validation questions ship a file, and ~73% need
  a live web search. This client handles the dataset and attachments; the *web* capability is a
  tool concern (see ``docs/scenarios-gaia.md``). :meth:`GAIADataset.self_contained` selects the
  small slice answerable from the attachment alone — the spike's target.

Everything caches under ``~/.cache/agentic-facets/gaia`` (override with ``FACETS_CACHE_DIR``).
Access is gated: you need an ``HF_TOKEN`` whose account accepted the dataset terms.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from facets.config import load_env, require_env

DATASET_REPO = "gaia-benchmark/GAIA"
_YEAR = "2023"  # the only release in the repo

_HF_ACCESS_HELP = (
    "Set HF_TOKEN to a Hugging Face token whose account has been granted access to the gated "
    "dataset. Visit https://huggingface.co/datasets/gaia-benchmark/GAIA and click "
    "'Agree and access repository' first."
)

# File extensions the minimal (Tier A) file tool can read as text/tables — the self-contained
# slice. Vision (png/jpg), audio (mp3), and archives (zip) are out of scope for the spike.
_TEXTUAL_EXTS = frozenset({"txt", "csv", "tsv", "json", "jsonld", "py", "xml", "md"})
_TABULAR_EXTS = frozenset({"xlsx", "xls"})
_PDF_EXTS = frozenset({"pdf"})
READABLE_EXTS = _TEXTUAL_EXTS | _TABULAR_EXTS | _PDF_EXTS


@dataclass(frozen=True)
class GAIAQuestion:
    """One GAIA question with its ground truth and (optional) single attachment.

    ``num_tools`` / ``num_steps`` come from the annotator metadata and record how many tools/steps
    the question was *designed* to need — useful for bucketing by intended complexity.
    """

    task_id: str
    question: str
    answer: str
    level: int
    file_name: str  # "" when the question has no attachment
    num_tools: int
    num_steps: int
    annotator_tools: str = ""

    @property
    def uid(self) -> str:
        """Alias so GAIA questions and OfficeQA questions share a ``.uid`` accessor."""
        return self.task_id

    @property
    def has_file(self) -> bool:
        return bool(self.file_name.strip())

    @property
    def file_ext(self) -> str:
        return self.file_name.rsplit(".", 1)[-1].lower() if "." in self.file_name else ""

    @property
    def needs_web(self) -> bool:
        """Whether the annotator listed a web browser / search engine among the tools."""
        tools = self.annotator_tools.lower()
        return any(w in tools for w in ("web browser", "search engine", "browser", "search"))

    @property
    def is_self_contained(self) -> bool:
        """Answerable from the attachment alone: has a readable file and needs no web search.

        This is the slice the initial spike targets — no web tool required.
        """
        return self.has_file and self.file_ext in READABLE_EXTS and not self.needs_web

    # ``source_files`` mirrors OfficeQA's Question so a scenario seam can treat the two uniformly.
    @property
    def source_files(self) -> tuple[str, ...]:
        return (self.file_name,) if self.has_file else ()


def _cache_dir() -> Path:
    load_env()
    base = os.environ.get("FACETS_CACHE_DIR")
    root = Path(base) if base else Path.home() / ".cache" / "agentic-facets"
    path = root / "gaia"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _hf_token() -> str:
    return require_env(
        "HF_TOKEN",
        why="GAIA is a gated Hugging Face dataset, so downloads need an access token.",
        how=_HF_ACCESS_HELP,
    )


def _annot_int(annotator: dict, key: str) -> int:
    """Parse an integer field from the annotator metadata, defaulting to 0."""
    raw = str((annotator or {}).get(key, "")).strip()
    try:
        return int(float(raw))
    except (ValueError, TypeError):
        return 0


class GAIADataset:
    """Loads GAIA questions for a split and resolves each question's attachment."""

    def __init__(self, split: str = "validation"):
        if split not in ("validation", "test"):
            raise ValueError("split must be 'validation' or 'test'")
        self.split = split
        self._meta_path = f"{_YEAR}/{split}/metadata.parquet"

    def _download(self, filename: str) -> Path:
        from huggingface_hub import hf_hub_download

        from facets.officeqa.data import _access_error  # reuse the shared gated-error mapper

        try:
            local = hf_hub_download(
                repo_id=DATASET_REPO,
                filename=filename,
                repo_type="dataset",
                token=_hf_token(),
                cache_dir=str(_cache_dir() / "hf"),
            )
        except Exception as exc:  # noqa: BLE001 — re-raise as an actionable credential error
            raise _access_error(filename, exc) from exc
        return Path(local)

    @lru_cache(maxsize=2)  # noqa: B019 — dataset instances are effectively per-split singletons
    def questions(self) -> tuple[GAIAQuestion, ...]:
        """Load and cache the split's question set from its parquet metadata."""
        rows = _read_parquet_rows(self._download(self._meta_path))
        return tuple(_row_to_question(r) for r in rows)

    def get(self, task_id: str) -> GAIAQuestion:
        for q in self.questions():
            if q.task_id == task_id:
                return q
        raise KeyError(f"No GAIA question with task_id={task_id!r} in split {self.split!r}.")

    def self_contained(self) -> list[GAIAQuestion]:
        """Questions answerable from their attachment alone (no web) — the spike's target slice."""
        return [q for q in self.questions() if q.is_self_contained]

    def attachment_path(self, question: GAIAQuestion) -> Path:
        """Download (and cache) the question's attachment, returning its local path."""
        if not question.has_file:
            raise ValueError(f"Question {question.task_id} has no attachment.")
        return self._download(f"{_YEAR}/{self.split}/{question.file_name}")


def _read_parquet_rows(path: Path) -> list[dict]:
    """Read a parquet file into a list of row dicts, with an actionable error if pyarrow is absent.

    GAIA's metadata is parquet; the standard library can't read it. We keep pyarrow an optional,
    lazily-imported dependency so importing this package never requires it.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        from facets.config import MissingCredential

        raise MissingCredential(
            "Reading GAIA metadata needs the 'pyarrow' package (GAIA ships parquet, not CSV).\n"
            "How to fix: `uv add pyarrow` (or `uv run --with pyarrow ...` for a one-off)."
        ) from exc
    return pq.read_table(path).to_pylist()


def _row_to_question(row: dict) -> GAIAQuestion:
    annotator = row.get("Annotator Metadata") or {}
    return GAIAQuestion(
        task_id=str(row.get("task_id", "")),
        question=str(row.get("Question", "")),
        answer=str(row.get("Final answer", "")),
        level=_coerce_level(row.get("Level")),
        file_name=str(row.get("file_name") or "").strip(),
        num_tools=_annot_int(annotator, "Number of tools"),
        num_steps=_annot_int(annotator, "Number of steps"),
        annotator_tools=str(annotator.get("Tools", "")),
    )


def _coerce_level(value: object) -> int:
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return 0
