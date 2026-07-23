"""State: the FACETS **State** axis — *what persists* and *where the source of truth lives*.

Release 0.1 ships the two lightest points on the spectrum: request-local context (just the
message list, held by the agent) and an in-memory :class:`TaskState` behind a
:class:`StateStore` protocol. The protocol is what matters — recipe 08 (durable, event-driven
execution) will drop in a Postgres/Lakebase-backed store *without changing the recipes that
depend on it*.
"""

from __future__ import annotations

import copy
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class PlanStep(BaseModel):
    """One unit of planned work — used by the planner–executor family (recipe 03+)."""

    id: str
    description: str
    status: StepStatus = StepStatus.PENDING
    result: Any | None = None


class TaskState(BaseModel):
    """Durable-shaped task state: goal, plan, artifacts, approvals, errors, checkpoints.

    In 0.1 it lives in memory, but the *shape* is what a durable store persists. Keeping the
    full shape now means later recipes add durability, not new fields.
    """

    task_id: str
    goal: str = ""
    plan: list[PlanStep] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    checkpoints: list[str] = Field(default_factory=list)

    def record_artifact(self, key: str, value: Any) -> None:
        self.artifacts[key] = value

    def checkpoint(self, label: str) -> None:
        self.checkpoints.append(label)


@runtime_checkable
class StateStore(Protocol):
    """Load/save task state. The seam that turns a synchronous demo into a resumable system."""

    async def load(self, task_id: str) -> TaskState: ...

    async def save(self, state: TaskState) -> None: ...


class InMemoryStateStore:
    """A dict-backed store. Deep-copies on the way in and out so callers can't mutate through
    a stale reference — the same guarantee a real store gives you across process boundaries."""

    def __init__(self) -> None:
        self._store: dict[str, TaskState] = {}

    async def load(self, task_id: str) -> TaskState:
        state = self._store.get(task_id)
        if state is None:
            state = TaskState(task_id=task_id)
            self._store[task_id] = state
        return state.model_copy(deep=True)

    async def save(self, state: TaskState) -> None:
        self._store[state.task_id] = copy.deepcopy(state)

    def exists(self, task_id: str) -> bool:
        return task_id in self._store
