"""Tracing: cost, latency, and step accounting.

The FACETS **Feedback** axis is about knowing whether the system succeeded; the trace is how
we *observe* what it did along the way. Every recipe emits a :class:`Trace` so the evaluation
harness can report model-call counts, token cost, and latency without instrumenting each recipe
by hand.

Wall-clock timing uses a monotonic clock injected at construction time so traces are
deterministic in tests (the default uses :func:`time.perf_counter`).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from facets.models import Usage


@dataclass
class Span:
    """A single timed unit of work — a model call, a tool call, or a nested agent."""

    name: str
    kind: str  # "model" | "tool" | "agent" | "step"
    attributes: dict[str, Any] = field(default_factory=dict)
    start: float = 0.0
    end: float = 0.0

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end - self.start)


class Trace:
    """A flat, ordered record of spans plus rolled-up usage.

    Kept intentionally simple (a list, not a tree): the recipes in this cookbook are shallow,
    and a flat log reads clearly in the evaluation output. A tree can come later if a recipe
    needs it.
    """

    def __init__(self, clock: Callable[[], float] | None = None):
        self._clock = clock or time.perf_counter
        self.spans: list[Span] = []
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.model_calls: int = 0

    @contextmanager
    def span(self, name: str, kind: str, **attributes: Any) -> Iterator[Span]:
        s = Span(name=name, kind=kind, attributes=attributes, start=self._clock())
        try:
            yield s
        finally:
            s.end = self._clock()
            self.spans.append(s)

    def record_usage(self, usage: Usage) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.model_calls += usage.model_calls

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def total_duration_s(self) -> float:
        return sum(s.duration_s for s in self.spans if s.kind in ("model", "tool"))

    @property
    def tool_calls(self) -> list[str]:
        """Names of tools invoked, in order — used to score tool-use correctness."""
        return [s.attributes.get("tool", s.name) for s in self.spans if s.kind == "tool"]

    def summary(self) -> dict[str, Any]:
        return {
            "model_calls": self.model_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "tool_calls": self.tool_calls,
            "duration_s": round(self.total_duration_s, 4),
        }
