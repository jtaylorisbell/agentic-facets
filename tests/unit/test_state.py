"""Unit tests for task state + the in-memory store's copy-on-load/save isolation."""

from facets.state import InMemoryStateStore, PlanStep, StepStatus, TaskState


async def test_load_creates_empty_state():
    store = InMemoryStateStore()
    state = await store.load("task-1")
    assert state.task_id == "task-1"
    assert state.plan == []


async def test_save_then_load_roundtrip():
    store = InMemoryStateStore()
    state = TaskState(task_id="t", goal="find root cause")
    state.record_artifact("diagnosis", {"root_cause": "schema mismatch"})
    state.plan.append(PlanStep(id="s1", description="query logs", status=StepStatus.DONE))
    await store.save(state)

    loaded = await store.load("t")
    assert loaded.goal == "find root cause"
    assert loaded.artifacts["diagnosis"]["root_cause"] == "schema mismatch"
    assert loaded.plan[0].status is StepStatus.DONE


async def test_loaded_state_is_isolated_copy():
    store = InMemoryStateStore()
    await store.save(TaskState(task_id="t", goal="original"))
    loaded = await store.load("t")
    loaded.goal = "mutated locally"  # must not leak back into the store
    reloaded = await store.load("t")
    assert reloaded.goal == "original"


async def test_saved_state_is_isolated_copy():
    store = InMemoryStateStore()
    state = TaskState(task_id="t")
    await store.save(state)
    state.errors.append("late mutation")  # must not affect what was stored
    reloaded = await store.load("t")
    assert reloaded.errors == []
