"""Evaluation: turning FACETS into evidence.

The cookbook's thesis — *"we built the same agent five ways; here's what changed"* — only
lands if the differences are measured. This module scores a recipe run against the metrics the
framework calls out: task success, tool-use correctness, model-call count, token cost, latency,
and (later) unsupported claims / policy violations / human-intervention rate.

Scorers are plain callables so recipes and the eval harness can mix built-ins with custom ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from facets.agents import AgentResult


@dataclass
class EvalCase:
    """One scenario to evaluate: the goal, plus the ground truth used by scorers."""

    id: str
    goal: str
    expected_root_cause: str | None = None
    expected_tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Score:
    name: str
    value: float
    detail: str = ""


@runtime_checkable
class Scorer(Protocol):
    """Grade a run against a case. Return a :class:`Score` in ``[0, 1]`` where higher is better."""

    name: str

    def __call__(self, case: EvalCase, result: AgentResult) -> Score: ...


class _NamedScorer:
    def __init__(self, name: str, fn: Any):
        self.name = name
        self._fn = fn

    def __call__(self, case: EvalCase, result: AgentResult) -> Score:
        return self._fn(case, result)


def task_success_scorer() -> Scorer:
    """1.0 if the run finished (not truncated) and names the expected root cause in its answer."""

    def score(case: EvalCase, result: AgentResult) -> Score:
        if result.hit_limit:
            return Score("task_success", 0.0, f"stopped: {result.stopped_reason}")
        if case.expected_root_cause is None:
            return Score("task_success", 1.0, "completed (no ground truth)")
        hit = case.expected_root_cause.lower() in result.answer.lower()
        detail = "root cause " + ("found" if hit else "missing")
        return Score("task_success", 1.0 if hit else 0.0, detail)

    return _NamedScorer("task_success", score)


def tool_correctness_scorer() -> Scorer:
    """Fraction of expected tools that were actually invoked during the run."""

    def score(case: EvalCase, result: AgentResult) -> Score:
        if not case.expected_tools:
            return Score("tool_correctness", 1.0, "no expected tools")
        used = set(result.trace.tool_calls)
        hit = [t for t in case.expected_tools if t in used]
        frac = len(hit) / len(case.expected_tools)
        detail = f"{len(hit)}/{len(case.expected_tools)} expected tools used"
        return Score("tool_correctness", frac, detail)

    return _NamedScorer("tool_correctness", score)


@dataclass
class RunReport:
    """Scores + cost metrics for a single case run through a single recipe."""

    case_id: str
    recipe: str
    scores: list[Score]
    model_calls: int
    total_tokens: int
    duration_s: float
    steps: int
    stopped_reason: str

    def score(self, name: str) -> float:
        for s in self.scores:
            if s.name == name:
                return s.value
        return float("nan")

    def as_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {"recipe": self.recipe, "case": self.case_id}
        for s in self.scores:
            row[s.name] = round(s.value, 3)
        row.update(
            model_calls=self.model_calls,
            total_tokens=self.total_tokens,
            duration_s=round(self.duration_s, 4),
            steps=self.steps,
            stopped=self.stopped_reason,
        )
        return row


@dataclass
class EvalReport:
    """A collection of run reports, comparable across recipes."""

    runs: list[RunReport] = field(default_factory=list)

    def add(self, run: RunReport) -> None:
        self.runs.append(run)

    def rows(self) -> list[dict[str, Any]]:
        return [r.as_row() for r in self.runs]


class Evaluator:
    """Applies a set of scorers to an :class:`AgentResult` and packages a :class:`RunReport`."""

    def __init__(self, scorers: Sequence[Scorer] | None = None):
        self.scorers: list[Scorer] = list(
            scorers or [task_success_scorer(), tool_correctness_scorer()]
        )

    def evaluate(self, case: EvalCase, recipe: str, result: AgentResult) -> RunReport:
        scores = [scorer(case, result) for scorer in self.scorers]
        return RunReport(
            case_id=case.id,
            recipe=recipe,
            scores=scores,
            model_calls=result.trace.model_calls,
            total_tokens=result.trace.total_tokens,
            duration_s=result.trace.total_duration_s,
            steps=result.steps,
            stopped_reason=result.stopped_reason,
        )
