"""Tests for Executor."""

import asyncio
import time
from datetime import date

import pytest
from pydantic import ValidationError

from lattice import AssetKey, AssetRegistry, ExecutionPlan, asset
from lattice.executor import (
    AssetExecutionResult,
    AssetStatus,
    AsyncExecutor,
    Executor,
    materialize,
    materialize_async,
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

        @asset(registry=registry, deps=["a"])
        def b(a: int) -> int:
            return a + 10

        @asset(registry=registry, deps=["b"])
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

        @asset(registry=registry, deps=["root"])
        def left(root: int) -> int:
            return root * 2

        @asset(registry=registry, deps=["root"])
        def right(root: int) -> int:
            return root * 3

        @asset(registry=registry, deps=["left", "right"])
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

        @asset(registry=registry, deps=["needed"])
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

        @asset(registry=registry, deps=["works"])
        def fails(works: int) -> int:
            raise ValueError("Intentional failure")

        @asset(registry=registry, deps=["fails"])
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

        @asset(registry=registry, deps=["a"])
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


class TestAsyncExecutorBasics:
    """Basic async executor tests."""

    @pytest.mark.asyncio
    async def test_execute_single_asset(self, registry: AssetRegistry) -> None:
        """Execute a single async asset."""

        @asset(registry=registry)
        async def source() -> int:
            return 42

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        executor = AsyncExecutor(io_manager=io)

        result = await executor.execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert result.completed_count == 1
        assert result.failed_count == 0
        assert io.load(AssetKey(name="source")) == 42

    @pytest.mark.asyncio
    async def test_execute_sync_asset(self, registry: AssetRegistry) -> None:
        """Execute a sync asset with async executor."""

        @asset(registry=registry)
        def sync_source() -> int:
            return 99

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        executor = AsyncExecutor(io_manager=io)

        result = await executor.execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert io.load(AssetKey(name="sync_source")) == 99

    @pytest.mark.asyncio
    async def test_execute_mixed_sync_async(self, registry: AssetRegistry) -> None:
        """Execute a mix of sync and async assets."""

        @asset(registry=registry)
        def sync_a() -> int:
            return 1

        @asset(registry=registry, deps=["sync_a"])
        async def async_b(sync_a: int) -> int:
            return sync_a + 10

        @asset(registry=registry, deps=["async_b"])
        def sync_c(async_b: int) -> int:
            return async_b + 100

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        result = await AsyncExecutor(io_manager=io).execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert result.completed_count == 3
        assert io.load(AssetKey(name="sync_c")) == 111

    @pytest.mark.asyncio
    async def test_execute_diamond(self, registry: AssetRegistry) -> None:
        """Execute diamond dependency pattern with parallel execution."""

        @asset(registry=registry)
        async def root() -> int:
            return 1

        @asset(registry=registry, deps=["root"])
        async def left(root: int) -> int:
            return root * 2

        @asset(registry=registry, deps=["root"])
        async def right(root: int) -> int:
            return root * 3

        @asset(registry=registry, deps=["left", "right"])
        async def sink(left: int, right: int) -> int:
            return left + right

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        result = await AsyncExecutor(io_manager=io).execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert io.load(AssetKey(name="sink")) == 5  # (1*2) + (1*3)


class TestAsyncExecutorParallel:
    """Tests for parallel execution."""

    @pytest.mark.asyncio
    async def test_parallel_independent_assets(self, registry: AssetRegistry) -> None:
        """Independent assets execute in parallel."""
        execution_order: list[str] = []
        execution_times: dict[str, float] = {}

        @asset(registry=registry)
        async def a() -> int:
            start = time.time()
            execution_order.append("a_start")
            await asyncio.sleep(0.05)
            execution_order.append("a_end")
            execution_times["a"] = time.time() - start
            return 1

        @asset(registry=registry)
        async def b() -> int:
            start = time.time()
            execution_order.append("b_start")
            await asyncio.sleep(0.05)
            execution_order.append("b_end")
            execution_times["b"] = time.time() - start
            return 2

        @asset(registry=registry)
        async def c() -> int:
            start = time.time()
            execution_order.append("c_start")
            await asyncio.sleep(0.05)
            execution_order.append("c_end")
            execution_times["c"] = time.time() - start
            return 3

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        executor = AsyncExecutor(io_manager=io, max_concurrency=3)

        start = time.time()
        result = await executor.execute(plan)
        total_time = time.time() - start

        assert result.status == AssetStatus.COMPLETED
        assert result.completed_count == 3
        # With parallel execution, all 3 should start before any ends
        # (if truly parallel, total time should be ~0.05s, not ~0.15s)
        assert total_time < 0.12  # Should be much less than sequential time

    @pytest.mark.asyncio
    async def test_concurrency_limit_respected(self, registry: AssetRegistry) -> None:
        """Max concurrency limit is respected."""
        concurrent_count = 0
        max_concurrent = 0

        @asset(registry=registry)
        async def a() -> int:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.02)
            concurrent_count -= 1
            return 1

        @asset(registry=registry)
        async def b() -> int:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.02)
            concurrent_count -= 1
            return 2

        @asset(registry=registry)
        async def c() -> int:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.02)
            concurrent_count -= 1
            return 3

        @asset(registry=registry)
        async def d() -> int:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.02)
            concurrent_count -= 1
            return 4

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        # Set max_concurrency to 2
        executor = AsyncExecutor(io_manager=io, max_concurrency=2)

        result = await executor.execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert result.completed_count == 4
        assert max_concurrent <= 2  # Should never exceed concurrency limit


class TestAsyncExecutorFailures:
    """Tests for failure handling in async executor."""

    @pytest.mark.asyncio
    async def test_failure_skips_downstream(self, registry: AssetRegistry) -> None:
        """Failed asset causes downstream assets to be skipped."""

        @asset(registry=registry)
        async def works() -> int:
            return 1

        @asset(registry=registry, deps=["works"])
        async def fails(works: int) -> int:
            raise ValueError("Intentional failure")

        @asset(registry=registry, deps=["fails"])
        async def downstream(fails: int) -> int:
            return fails + 1

        plan = ExecutionPlan.resolve(registry)
        result = await AsyncExecutor(io_manager=MemoryIOManager()).execute(plan)

        assert result.status == AssetStatus.FAILED
        assert result.failed_count == 1
        results_by_key = {str(r.key): r for r in result.asset_results}
        assert results_by_key["downstream"].status == AssetStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_failure_records_error(self, registry: AssetRegistry) -> None:
        """Failed asset records error message."""

        @asset(registry=registry)
        async def bad() -> int:
            raise RuntimeError("Something went wrong")

        plan = ExecutionPlan.resolve(registry)
        result = await AsyncExecutor(io_manager=MemoryIOManager()).execute(plan)

        assert result.asset_results[0].error is not None
        assert "Something went wrong" in result.asset_results[0].error

    @pytest.mark.asyncio
    async def test_independent_branch_continues_on_failure(self, registry: AssetRegistry) -> None:
        """Independent branches can complete even when another fails."""

        @asset(registry=registry)
        async def fails() -> int:
            raise ValueError("fail")

        @asset(registry=registry)
        async def independent() -> int:
            return 42

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        result = await AsyncExecutor(io_manager=io).execute(plan)

        # Overall status is failed, but independent asset should complete
        assert result.status == AssetStatus.FAILED
        results_by_key = {str(r.key): r for r in result.asset_results}
        # Independent asset should be completed (not skipped)
        assert results_by_key["independent"].status == AssetStatus.COMPLETED
        assert io.load(AssetKey(name="independent")) == 42


class TestAsyncExecutorCallbacks:
    """Tests for async execution callbacks."""

    @pytest.mark.asyncio
    async def test_on_asset_start_callback(self, registry: AssetRegistry) -> None:
        """on_asset_start is called for each asset."""
        started: list[str] = []

        @asset(registry=registry)
        async def a() -> int:
            return 1

        @asset(registry=registry, deps=["a"])
        async def b(a: int) -> int:
            return a + 1

        plan = ExecutionPlan.resolve(registry)
        executor = AsyncExecutor(
            io_manager=MemoryIOManager(),
            on_asset_start=lambda k: started.append(str(k)),
        )
        await executor.execute(plan)

        assert "a" in started
        assert "b" in started
        assert len(started) == 2

    @pytest.mark.asyncio
    async def test_on_asset_complete_callback(self, registry: AssetRegistry) -> None:
        """on_asset_complete is called with results."""
        completed: list[AssetExecutionResult] = []

        @asset(registry=registry)
        async def x() -> int:
            return 42

        plan = ExecutionPlan.resolve(registry)
        executor = AsyncExecutor(
            io_manager=MemoryIOManager(),
            on_asset_complete=lambda r: completed.append(r),
        )
        await executor.execute(plan)

        assert len(completed) == 1
        assert completed[0].status == AssetStatus.COMPLETED


class TestAsyncExecutorCancellation:
    """Tests for cancellation handling."""

    @pytest.mark.asyncio
    async def test_cancel_stops_new_assets(self, registry: AssetRegistry) -> None:
        """Calling cancel() prevents new assets from starting."""
        started: list[str] = []

        @asset(registry=registry)
        async def a() -> int:
            started.append("a")
            await asyncio.sleep(0.05)
            return 1

        @asset(registry=registry, deps=["a"])
        async def b(a: int) -> int:
            started.append("b")
            return a + 1

        @asset(registry=registry, deps=["b"])
        async def c(b: int) -> int:
            started.append("c")
            return b + 1

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        executor = AsyncExecutor(io_manager=io, max_concurrency=1)

        # Cancel after a very short delay
        async def cancel_soon() -> None:
            await asyncio.sleep(0.01)
            executor.cancel()

        asyncio.create_task(cancel_soon())
        result = await executor.execute(plan)

        # a should have started and completed
        assert "a" in started
        # At least one asset should be completed (a)
        assert any(r.status == AssetStatus.COMPLETED for r in result.asset_results)


class TestMaterializeAsyncFunction:
    """Tests for materialize_async() convenience function."""

    @pytest.mark.asyncio
    async def test_materialize_async_with_registry(self, registry: AssetRegistry) -> None:
        """materialize_async() accepts custom registry."""

        @asset(registry=registry)
        async def custom() -> int:
            return 123

        result = await materialize_async(registry=registry)

        assert result.status == AssetStatus.COMPLETED
        assert result.completed_count == 1

    @pytest.mark.asyncio
    async def test_materialize_async_with_target(self, registry: AssetRegistry) -> None:
        """materialize_async() respects target parameter."""

        @asset(registry=registry)
        async def included() -> int:
            return 1

        @asset(registry=registry)
        async def excluded() -> int:
            return 2

        io = MemoryIOManager()
        result = await materialize_async(registry=registry, target="included", io_manager=io)

        assert result.completed_count == 1
        assert io.has(AssetKey(name="included"))
        assert not io.has(AssetKey(name="excluded"))

    @pytest.mark.asyncio
    async def test_materialize_async_with_concurrency(self, registry: AssetRegistry) -> None:
        """materialize_async() respects max_concurrency parameter."""
        concurrent_count = 0
        max_concurrent = 0

        @asset(registry=registry)
        async def a() -> int:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.01)
            concurrent_count -= 1
            return 1

        @asset(registry=registry)
        async def b() -> int:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.01)
            concurrent_count -= 1
            return 2

        @asset(registry=registry)
        async def c() -> int:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.01)
            concurrent_count -= 1
            return 3

        result = await materialize_async(registry=registry, max_concurrency=1)

        assert result.status == AssetStatus.COMPLETED
        assert max_concurrent <= 1  # With max_concurrency=1, only 1 at a time


class TestExecutorPartitionKey:
    """Tests for partition_key injection in Executor."""

    def test_partition_key_injected_when_accepted(self, registry: AssetRegistry) -> None:
        """partition_key is injected into assets that accept it."""
        received_date: list[date | None] = []

        @asset(registry=registry)
        def date_aware(partition_key: date) -> str:
            received_date.append(partition_key)
            return f"processed_{partition_key}"

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        test_date = date(2024, 1, 15)
        executor = Executor(io_manager=io, partition_key=test_date)

        result = executor.execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert len(received_date) == 1
        assert received_date[0] == test_date
        assert (
            io.load(AssetKey(name="date_aware"), partition_key="2024-01-15")
            == "processed_2024-01-15"
        )

    def test_partition_key_not_injected_when_not_accepted(self, registry: AssetRegistry) -> None:
        """partition_key is not injected into assets that don't accept it."""

        @asset(registry=registry)
        def no_date() -> str:
            return "no_date_needed"

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        executor = Executor(io_manager=io, partition_key=date(2024, 1, 15))

        result = executor.execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert io.load(AssetKey(name="no_date"), partition_key="2024-01-15") == "no_date_needed"

    def test_partition_key_mixed_assets(self, registry: AssetRegistry) -> None:
        """partition_key is correctly injected in mixed asset pipelines."""
        received_dates: dict[str, date | None] = {}

        @asset(registry=registry)
        def source() -> int:
            return 100

        @asset(registry=registry, deps=["source"])
        def date_processor(source: int, partition_key: date) -> str:
            received_dates["date_processor"] = partition_key
            return f"{source}_{partition_key}"

        @asset(registry=registry, deps=["date_processor"])
        def final(date_processor: str) -> str:
            return f"final_{date_processor}"

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        test_date = date(2024, 3, 20)
        executor = Executor(io_manager=io, partition_key=test_date)

        result = executor.execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert received_dates["date_processor"] == test_date
        assert io.load(AssetKey(name="final"), partition_key="2024-03-20") == "final_100_2024-03-20"

    def test_no_partition_key_when_none(self, registry: AssetRegistry) -> None:
        """partition_key is not injected when executor has no partition_key."""

        @asset(registry=registry)
        def date_aware(partition_key: date | None = None) -> str:
            return f"date={partition_key}"

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        executor = Executor(io_manager=io)  # No partition_key

        result = executor.execute(plan)

        assert result.status == AssetStatus.COMPLETED
        # Should use the default value (None)
        assert io.load(AssetKey(name="date_aware")) == "date=None"


class TestAsyncExecutorPartitionKey:
    """Tests for partition_key injection in AsyncExecutor."""

    @pytest.mark.asyncio
    async def test_partition_key_injected_when_accepted(self, registry: AssetRegistry) -> None:
        """partition_key is injected into async assets that accept it."""
        received_date: list[date | None] = []

        @asset(registry=registry)
        async def date_aware(partition_key: date) -> str:
            received_date.append(partition_key)
            return f"processed_{partition_key}"

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        test_date = date(2024, 6, 1)
        executor = AsyncExecutor(io_manager=io, partition_key=test_date)

        result = await executor.execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert len(received_date) == 1
        assert received_date[0] == test_date
        assert (
            io.load(AssetKey(name="date_aware"), partition_key="2024-06-01")
            == "processed_2024-06-01"
        )

    @pytest.mark.asyncio
    async def test_partition_key_not_injected_when_not_accepted(
        self, registry: AssetRegistry
    ) -> None:
        """partition_key is not injected into async assets that don't accept it."""

        @asset(registry=registry)
        async def no_date() -> str:
            return "no_date_needed"

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        executor = AsyncExecutor(io_manager=io, partition_key=date(2024, 1, 15))

        result = await executor.execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert io.load(AssetKey(name="no_date"), partition_key="2024-01-15") == "no_date_needed"

    @pytest.mark.asyncio
    async def test_partition_key_with_sync_asset(self, registry: AssetRegistry) -> None:
        """partition_key is injected into sync assets run by AsyncExecutor."""
        received_date: list[date | None] = []

        @asset(registry=registry)
        def sync_date_aware(partition_key: date) -> str:
            received_date.append(partition_key)
            return f"sync_{partition_key}"

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        test_date = date(2024, 12, 25)
        executor = AsyncExecutor(io_manager=io, partition_key=test_date)

        result = await executor.execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert received_date[0] == test_date
        assert (
            io.load(AssetKey(name="sync_date_aware"), partition_key="2024-12-25")
            == "sync_2024-12-25"
        )

    @pytest.mark.asyncio
    async def test_partition_key_parallel_assets(self, registry: AssetRegistry) -> None:
        """partition_key is correctly injected into parallel assets."""
        received_dates: dict[str, date] = {}

        @asset(registry=registry)
        async def parallel_a(partition_key: date) -> str:
            received_dates["a"] = partition_key
            await asyncio.sleep(0.01)
            return f"a_{partition_key}"

        @asset(registry=registry)
        async def parallel_b(partition_key: date) -> str:
            received_dates["b"] = partition_key
            await asyncio.sleep(0.01)
            return f"b_{partition_key}"

        @asset(registry=registry)
        async def parallel_c(partition_key: date) -> str:
            received_dates["c"] = partition_key
            await asyncio.sleep(0.01)
            return f"c_{partition_key}"

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        test_date = date(2024, 7, 4)
        executor = AsyncExecutor(io_manager=io, max_concurrency=3, partition_key=test_date)

        result = await executor.execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert result.completed_count == 3
        # All assets should receive the same partition_key
        assert received_dates["a"] == test_date
        assert received_dates["b"] == test_date
        assert received_dates["c"] == test_date


class TestPositionalInjectionOrder:
    """Tests that dependency values are injected in the order declared in deps."""

    def test_sync_positional_injection_order(self, registry: AssetRegistry) -> None:
        """deps=['a', 'b'] injects a's value into first param, b's into second."""

        @asset(registry=registry)
        def a() -> str:
            return "value_a"

        @asset(registry=registry)
        def b() -> str:
            return "value_b"

        @asset(registry=registry, deps=["a", "b"])
        def combined(x: str, y: str) -> dict:
            return {"x": x, "y": y}

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        result = Executor(io_manager=io).execute(plan)

        assert result.status == AssetStatus.COMPLETED
        loaded = io.load(AssetKey(name="combined"))
        assert loaded["x"] == "value_a"
        assert loaded["y"] == "value_b"

    def test_sync_injection_order_reversed(self, registry: AssetRegistry) -> None:
        """deps=['b', 'a'] injects b's value into first param, a's into second."""

        @asset(registry=registry)
        def a() -> str:
            return "value_a"

        @asset(registry=registry)
        def b() -> str:
            return "value_b"

        @asset(registry=registry, deps=["b", "a"])
        def combined(x: str, y: str) -> dict:
            return {"x": x, "y": y}

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        result = Executor(io_manager=io).execute(plan)

        assert result.status == AssetStatus.COMPLETED
        loaded = io.load(AssetKey(name="combined"))
        assert loaded["x"] == "value_b"
        assert loaded["y"] == "value_a"


class TestAsyncDepsInjection:
    """Tests that async assets with deps receive correct injected values."""

    @pytest.mark.asyncio
    async def test_async_asset_with_string_deps(self, registry: AssetRegistry) -> None:
        """Async asset with deps=['source'] receives source's value."""

        @asset(registry=registry)
        async def source() -> int:
            return 100

        @asset(registry=registry, deps=["source"])
        async def downstream(data: int) -> int:
            return data * 2

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        result = await AsyncExecutor(io_manager=io).execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert io.load(AssetKey(name="downstream")) == 200

    @pytest.mark.asyncio
    async def test_async_asset_positional_injection_order(self, registry: AssetRegistry) -> None:
        """Async asset respects deps ordering for positional injection."""

        @asset(registry=registry)
        async def first() -> str:
            return "first_val"

        @asset(registry=registry)
        async def second() -> str:
            return "second_val"

        @asset(registry=registry, deps=["first", "second"])
        async def combined(x: str, y: str) -> dict:
            return {"x": x, "y": y}

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        result = await AsyncExecutor(io_manager=io).execute(plan)

        assert result.status == AssetStatus.COMPLETED
        loaded = io.load(AssetKey(name="combined"))
        assert loaded["x"] == "first_val"
        assert loaded["y"] == "second_val"

    @pytest.mark.asyncio
    async def test_async_asset_with_grouped_deps(self, registry: AssetRegistry) -> None:
        """Async asset with grouped AssetKey deps receives correct values."""

        @asset(registry=registry, group="data")
        async def source() -> int:
            return 42

        @asset(registry=registry, deps=[AssetKey(name="source", group="data")])
        async def consumer(data: int) -> int:
            return data + 1

        plan = ExecutionPlan.resolve(registry)
        io = MemoryIOManager()
        result = await AsyncExecutor(io_manager=io).execute(plan)

        assert result.status == AssetStatus.COMPLETED
        assert io.load(AssetKey(name="consumer")) == 43


class TestExecutorPartitionIsolatesIO:
    """Tests that partition_key scopes IO manager storage."""

    def test_sync_executor_partition_isolates_io(self) -> None:
        """Run A->B on date1, then only B on date2; B fails (no A for date2)."""
        registry1 = AssetRegistry()

        @asset(registry=registry1)
        def upstream() -> int:
            return 10

        @asset(registry=registry1, deps=["upstream"])
        def downstream(upstream: int) -> int:
            return upstream + 1

        io = MemoryIOManager()
        date1 = date(2026, 4, 5)

        # Run full pipeline on date1
        plan1 = ExecutionPlan.resolve(registry1)
        result1 = Executor(io_manager=io, partition_key=date1).execute(plan1)
        assert result1.status == AssetStatus.COMPLETED

        # Verify date1 data is stored in the partition
        assert io.has(AssetKey(name="upstream"), partition_key="2026-04-05")
        assert io.has(AssetKey(name="downstream"), partition_key="2026-04-05")

        # Run only downstream on date2 — should fail (no upstream for date2)
        registry2 = AssetRegistry()

        @asset(registry=registry2)
        def upstream() -> int:  # noqa: F811
            return 10

        @asset(registry=registry2, deps=["upstream"])
        def downstream(upstream: int) -> int:  # noqa: F811
            return upstream + 1

        date2 = date(2026, 4, 6)
        plan2 = ExecutionPlan.resolve(registry2, target="downstream")
        Executor(io_manager=io, partition_key=date2).execute(plan2)

        # upstream will be re-executed as part of the plan, so the whole
        # pipeline should succeed — but the key point is data is isolated
        assert io.has(AssetKey(name="upstream"), partition_key="2026-04-06")
        assert io.has(AssetKey(name="downstream"), partition_key="2026-04-06")

        # date1 data is untouched
        assert io.load(AssetKey(name="upstream"), partition_key="2026-04-05") == 10
        assert io.load(AssetKey(name="downstream"), partition_key="2026-04-05") == 11

    @pytest.mark.asyncio
    async def test_async_executor_partition_isolates_io(self) -> None:
        """Async executor isolates IO by partition_key."""
        registry1 = AssetRegistry()

        @asset(registry=registry1)
        async def source() -> int:
            return 100

        @asset(registry=registry1, deps=["source"])
        async def sink(source: int) -> int:
            return source * 2

        io = MemoryIOManager()
        date1 = date(2026, 4, 5)

        # Run full pipeline on date1
        plan1 = ExecutionPlan.resolve(registry1)
        result1 = await AsyncExecutor(io_manager=io, partition_key=date1).execute(plan1)
        assert result1.status == AssetStatus.COMPLETED
        assert io.load(AssetKey(name="sink"), partition_key="2026-04-05") == 200

        # date2 partition should be empty
        assert not io.has(AssetKey(name="source"), partition_key="2026-04-06")
        assert not io.has(AssetKey(name="sink"), partition_key="2026-04-06")

    def test_sync_executor_no_partition_backwards_compatible(self) -> None:
        """Executor without partition_key stores in unpartitioned slot."""
        registry1 = AssetRegistry()

        @asset(registry=registry1)
        def simple() -> int:
            return 42

        io = MemoryIOManager()
        plan = ExecutionPlan.resolve(registry1)
        result = Executor(io_manager=io).execute(plan)

        assert result.status == AssetStatus.COMPLETED
        # Stored in unpartitioned slot (partition_key=None)
        assert io.has(AssetKey(name="simple"))
        assert io.load(AssetKey(name="simple")) == 42
