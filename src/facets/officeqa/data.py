"""OfficeQA dataset client.

OfficeQA is Databricks' benchmark for document-grounded reasoning: hard questions whose answers
live inside U.S. Treasury Bulletin documents (1939–2025). See
https://huggingface.co/datasets/databricks/officeqa (gated, CC-BY-SA-4.0).

This client does two things, both against the real dataset:

1. Loads the question set (``officeqa_pro.csv`` / ``officeqa_full.csv``) — each row is a
   question, its ground-truth answer, and the ``source_files`` that contain the answer.
2. Fetches and caches the transformed-text version of a corpus document on demand, so the
   agent tools can actually read what they cite.

Everything is cached under ``~/.cache/agentic-facets/officeqa`` (override with
``FACETS_CACHE_DIR``) so repeated runs do not re-download. Access is gated: you need an
``HF_TOKEN`` for an account that has accepted the dataset terms. When that is missing the
client raises a :class:`~facets.config.MissingCredential` with instructions rather than a
cryptic HTTP 401.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from facets.config import load_env, require_env

DATASET_REPO = "databricks/officeqa"
# The corpus lives here inside the dataset repo; the transformed .txt files are what the agents
# read (parsed from the source PDFs into LLM-friendly markdown-ish tables).
_TRANSFORMED_PREFIX = "treasury_bulletins_parsed/transformed"

_HF_ACCESS_HELP = (
    "Set HF_TOKEN to a Hugging Face token whose account has been granted access to the gated "
    "dataset. Visit https://huggingface.co/datasets/databricks/officeqa and click "
    "'Agree and access repository' first."
)


@dataclass(frozen=True)
class Question:
    """One OfficeQA question with its ground truth and the documents that answer it."""

    uid: str
    question: str
    answer: str
    source_files: tuple[str, ...]
    source_docs: tuple[str, ...]
    difficulty: str


def _cache_dir() -> Path:
    load_env()
    base = os.environ.get("FACETS_CACHE_DIR")
    root = Path(base) if base else Path.home() / ".cache" / "agentic-facets"
    path = root / "officeqa"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _hf_token() -> str:
    return require_env(
        "HF_TOKEN",
        why="OfficeQA is a gated Hugging Face dataset, so downloads need an access token.",
        how=_HF_ACCESS_HELP,
    )


def _split_files(field: str) -> tuple[str, ...]:
    """source_files may hold several filenames separated by newlines or commas."""
    parts = [p.strip() for chunk in field.split("\n") for p in chunk.split(",")]
    return tuple(p for p in parts if p)


class OfficeQADataset:
    """Loads OfficeQA questions and resolves the corpus documents they reference."""

    def __init__(self, subset: str = "pro"):
        if subset not in ("pro", "full"):
            raise ValueError("subset must be 'pro' or 'full'")
        self.subset = subset
        self._csv_name = f"officeqa_{subset}.csv"

    def _download(self, filename: str) -> Path:
        """Fetch a file from the dataset repo into the local cache and return its path."""
        from huggingface_hub import hf_hub_download

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

    @lru_cache(maxsize=2)  # noqa: B019 — dataset instances are effectively singletons per subset
    def questions(self) -> tuple[Question, ...]:
        """Load and cache the question set."""
        csv_path = self._download(self._csv_name)
        rows: list[Question] = []
        with csv_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append(
                    Question(
                        uid=row["uid"],
                        question=row["question"],
                        answer=row["answer"],
                        source_files=_split_files(row.get("source_files", "")),
                        source_docs=_split_files(row.get("source_docs", "")),
                        difficulty=row.get("difficulty", ""),
                    )
                )
        return tuple(rows)

    def get(self, uid: str) -> Question:
        for q in self.questions():
            if q.uid == uid:
                return q
        raise KeyError(f"No OfficeQA question with uid={uid!r} in subset {self.subset!r}.")

    def sample(self, n: int) -> list[Question]:
        """First ``n`` questions — deterministic, for reproducible demos and evals."""
        return list(self.questions()[:n])

    def read_document(self, source_file: str) -> str:
        """Return the transformed text of a corpus document, downloading + caching if needed.

        ``source_file`` is a name like ``treasury_bulletin_1941_01.txt`` as it appears in a
        question's ``source_files``.
        """
        name = source_file.strip()
        if not name.endswith(".txt"):
            name = f"{name}.txt"
        path = self._download(f"{_TRANSFORMED_PREFIX}/{name}")
        return path.read_text(encoding="utf-8")

    def document_exists(self, source_file: str) -> bool:
        try:
            self.read_document(source_file)
            return True
        except Exception:  # noqa: BLE001
            return False


def _access_error(filename: str, exc: Exception) -> Exception:
    """Turn an HF download failure into either a credential error or the original exception."""
    from facets.config import MissingCredential

    text = str(exc).lower()
    if "401" in text or "403" in text or "gated" in text or "restricted" in text:
        return MissingCredential(
            f"Cannot access '{filename}' in {DATASET_REPO}. {_HF_ACCESS_HELP}"
        )
    return exc
