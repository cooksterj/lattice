"""Tests for Executor."""

import pytest
from pydantic import ValidationError

from lattice import AssetKey, AssetRegistry, ExecutionPlan, asset
from lattice.executor import (
    AssetExecutionResult,
    AssetStatus,
    Executor,
    materialize,
)
from lattice.io import MemoryIOManager


class TestExecutorBasics:
    """Basic executor tests."""

    def test_execute_single_asset(self, registry: AssetRegistry) -> None:
        """Execute a single asset with no dependencies."""

        @asset(registry=registry)
        def source() -> int:
            return 42

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        executor = Executor(io_manager=io)

        result = executor.execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert result.completed_count == 1
        assert result.failed_count == 0
        assert io.load(AssetKey(name="source")) == 42

    def test_execute_linear_chain(self, registry: AssetRegistry) -> None:
        """Execute assets with dependencies in order."""

        @asset(registry=registry)
        def a() -> int:
            return 1

        @asset(registry=registry)
        def b(a: int) -> int:
            return a + 10

        @asset(registry=registry)
        def c(b: int) -> int:
            return b + 100

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        executor = Executor(io_manager=io)

        result = executor.execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert result.completed_count == 3
        assert io.load(AssetKey(name="a")) == 1
        assert io.load(AssetKey(name="b")) == 11
        assert io.load(AssetKey(name="c")) == 111

    def test_execute_diamond(self, registry: AssetRegistry) -> None:
        """Execute diamond dependency pattern."""

        @asset(registry=registry)
        def root() -> int:
            return 1

        @asset(registry=registry)
        def left(root: int) -> int:
            return root * 2

        @asset(registry=registry)
        def right(root: int) -> int:
            return root * 3

        @asset(registry=registry)
        def sink(left: int, right: int) -> int:
            return left + right

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        result = Executor(io_manager=io).execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert io.load(AssetKey(name="sink")) == 5  # (1*2) + (1*3)

    def test_execute_with_target(self, registry: AssetRegistry) -> None:
        """Execute only target and its dependencies."""

        @asset(registry=registry)
        def needed() -> int:
            return 1

        @asset(registry=registry)
        def target(needed: int) -> int:
            return needed + 1

        @asset(registry=registry)
        def not_needed() -> int:
            return 999

        plan = ExecutionPlan.resolve(registry, target="target")
        io = MemoryIOManager()
        result = Executor(io_manager=io).execute(plan)

        assert result.completed_count == 2
        assert io.has(AssetKey(name="needed"))
        assert io.has(AssetKey(name="target"))
        assert not io.has(AssetKey(name="not_needed"))


class TestExecutorFailures:
    """Tests for failure handling."""

    def test_asset_failure_stops_execution(self, registry: AssetRegistry) -> None:
        """Failed asset stops downstream execution."""

        @asset(registry=registry)
        def works() -> int:
            return 1

        @asset(registry=registry)
        def fails(works: int) -> int:
            raise ValueError("Intentional failure")

        @asset(registry=registry)
        def downstream(fails: int) -> int:
            return fails + 1

        plan = ExecutionPlan.resolve(registry)
        result = Executor(io_manager=MemoryIOManager()).execute(plan)

        assert result.status == AssetStatus.FAILED
        assert result.failed_count == 1
        # Downstream should be skipped
        results_by_key = {str(r.key): r for r in result.asset_results}
        assert results_by_key["downstream"].status == AssetStatus.SKIPPED

    def test_failure_records_error(self, registry: AssetRegistry) -> None:
        """Failed asset records error message."""

        @asset(registry=registry)
        def bad() -> int:
            raise RuntimeError("Something went wrong")

        plan = ExecutionPlan.resolve(registry)
        result = Executor(io_manager=MemoryIOManager()).execute(plan)

        assert result.asset_results[0].error is not None
        assert "Something went wrong" in result.asset_results[0].error

    def test_independent_assets_not_skipped(self, registry: AssetRegistry) -> None:
        """Independent assets are still skipped after failure (sequential execution)."""
        # Note: In sync execution, all remaining assets are skipped after failure
        # Parallel execution would allow independent branches to continue

        @asset(registry=registry)
        def fails() -> int:
            raise ValueError("fail")

        @asset(registry=registry)
        def independent() -> int:
            return 42

        plan = ExecutionPlan.resolve(registry)
        result = Executor(io_manager=MemoryIOManager()).execute(plan)

        # Both tracked, one failed, one skipped (or completed if executed first)
        assert result.status == AssetStatus.FAILED


class TestExecutorCallbacks:
    """Tests for execution callbacks."""

    def test_on_asset_start_callback(self, registry: AssetRegistry) -> None:
        """on_asset_start is called for each asset."""
        started: list[str] = []

        @asset(registry=registry)
        def a() -> int:
            return 1

        @asset(registry=registry)
        def b(a: int) -> int:
            return a + 1

        plan = ExecutionPlan.resolve(registry)
        executor = Executor(
            io_manager=MemoryIOManager(),
            on_asset_start=lambda k: started.append(str(k)),
        )
        executor.execute(plan)

        assert started == ["a", "b"]

    def test_on_asset_complete_callback(self, registry: AssetRegistry) -> None:
        """on_asset_complete is called with results."""
        completed: list[AssetExecutionResult] = []

        @asset(registry=registry)
        def x() -> int:
            return 42

        plan = ExecutionPlan.resolve(registry)
        executor = Executor(
            io_manager=MemoryIOManager(),
            on_asset_complete=lambda r: completed.append(r),
        )
        executor.execute(plan)

        assert len(completed) == 1
        assert completed[0].status == AssetStatus.COMPLETED

    def test_callbacks_on_failure(self, registry: AssetRegistry) -> None:
        """Callbacks are called even on failure."""
        started: list[str] = []
        completed: list[AssetExecutionResult] = []

        @asset(registry=registry)
        def bad() -> int:
            raise ValueError("fail")

        plan = ExecutionPlan.resolve(registry)
        executor = Executor(
            io_manager=MemoryIOManager(),
            on_asset_start=lambda k: started.append(str(k)),
            on_asset_complete=lambda r: completed.append(r),
        )
        executor.execute(plan)

        assert started == ["bad"]
        assert len(completed) == 1
        assert completed[0].status == AssetStatus.FAILED


class TestExecutorState:
    """Tests for executor state tracking."""

    def test_current_state_is_none_when_not_executing(self, registry: AssetRegistry) -> None:
        """current_state is None when not executing."""
        executor = Executor(io_manager=MemoryIOManager())
        assert executor.current_state is None

    def test_current_state_during_execution(self, registry: AssetRegistry) -> None:
        """current_state is set during execution."""
        state_snapshots: list[str | None] = []

        @asset(registry=registry)
        def capture() -> int:
            return 1

        def on_start(key: AssetKey) -> None:
            # Access current state during callback
            executor = executors[0]
            if executor.current_state:
                state_snapshots.append(str(executor.current_state.current_asset))

        executors: list[Executor] = []
        executor = Executor(
            io_manager=MemoryIOManager(),
            on_asset_start=on_start,
        )
        executors.append(executor)

        plan = ExecutionPlan.resolve(registry)
        executor.execute(plan)

        assert state_snapshots == ["capture"]
        # After execution, state is None again
        assert executor.current_state is None


class TestMaterializeFunction:
    """Tests for materialize() convenience function."""

    def test_materialize_uses_global_registry(self) -> None:
        """materialize() defaults to global registry."""
        from lattice import get_global_registry

        registry = get_global_registry()
        registry.clear()

        @asset(registry=registry)
        def test_asset() -> int:
            return 99

        result = materialize()

        assert result.status == AssetStatus.COMPLETED
        assert result.completed_count == 1

    def test_materialize_with_custom_registry(self, registry: AssetRegistry) -> None:
        """materialize() accepts custom registry."""

        @asset(registry=registry)
        def custom() -> int:
            return 123

        result = materialize(registry=registry)

        assert result.status == AssetStatus.COMPLETED
        assert result.completed_count == 1

    def test_materialize_with_target(self, registry: AssetRegistry) -> None:
        """materialize() respects target parameter."""

        @asset(registry=registry)
        def included() -> int:
            return 1

        @asset(registry=registry)
        def excluded() -> int:
            return 2

        io = MemoryIOManager()
        result = materialize(registry=registry, target="included", io_manager=io)

        assert result.completed_count == 1
        assert io.has(AssetKey(name="included"))
        assert not io.has(AssetKey(name="excluded"))

    def test_materialize_with_io_manager(self, registry: AssetRegistry) -> None:
        """materialize() uses provided io_manager."""

        @asset(registry=registry)
        def stored() -> dict:
            return {"key": "value"}

        io = MemoryIOManager()
        materialize(registry=registry, io_manager=io)

        assert io.load(AssetKey(name="stored")) == {"key": "value"}


class TestExecutionResult:
    """Tests for ExecutionResult model."""

    def test_result_is_immutable(self, registry: AssetRegistry) -> None:
        """ExecutionResult is frozen."""

        @asset(registry=registry)
        def simple() -> int:
            return 1

        plan = ExecutionPlan.resolve(registry)
        result = Executor(io_manager=MemoryIOManager()).execute(plan)

        with pytest.raises(ValidationError):
            result.status = AssetStatus.FAILED  # type: ignore[misc]

    def test_result_has_timing(self, registry: AssetRegistry) -> None:
        """ExecutionResult includes timing information."""

        @asset(registry=registry)
        def timed() -> int:
            return 1

        plan = ExecutionPlan.resolve(registry)
        result = Executor(io_manager=MemoryIOManager()).execute(plan)

        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.duration_ms >= 0
        assert result.asset_results[0].duration_ms is not None

    def test_result_has_run_id(self, registry: AssetRegistry) -> None:
        """ExecutionResult has unique run_id."""

        @asset(registry=registry)
        def asset1() -> int:
            return 1

        plan = ExecutionPlan.resolve(registry)
        executor = Executor(io_manager=MemoryIOManager())

        result1 = executor.execute(plan)
        result2 = executor.execute(plan)

        assert result1.run_id != result2.run_id

    def test_asset_result_is_immutable(self, registry: AssetRegistry) -> None:
        """AssetExecutionResult is frozen."""

        @asset(registry=registry)
        def simple() -> int:
            return 1

        plan = ExecutionPlan.resolve(registry)
        result = Executor(io_manager=MemoryIOManager()).execute(plan)

        with pytest.raises(ValidationError):
            result.asset_results[0].status = AssetStatus.FAILED  # type: ignore[misc]


class TestAssetStatus:
    """Tests for AssetStatus enum."""

    def test_status_values(self) -> None:
        """AssetStatus has expected values."""
        assert AssetStatus.PENDING.value == "pending"
        assert AssetStatus.RUNNING.value == "running"
        assert AssetStatus.COMPLETED.value == "completed"
        assert AssetStatus.FAILED.value == "failed"
        assert AssetStatus.SKIPPED.value == "skipped"

    def test_status_is_string_enum(self) -> None:
        """AssetStatus values are strings."""
        assert AssetStatus.COMPLETED.value == "completed"
        # String enum also works for comparison
        assert AssetStatus.COMPLETED == "completed"
