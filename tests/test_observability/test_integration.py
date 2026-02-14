"""Integration tests for observability module."""

from lattice import AssetKey, AssetRegistry, MemoryIOManager, asset
from lattice.observability import (
    CheckRegistry,
    SQLiteRunHistoryStore,
    materialize_with_observability,
)
from lattice.observability.models import CheckStatus


class TestMaterializeWithObservability:
    """Integration tests for materialize_with_observability."""

    def test_basic_execution(self, registry: AssetRegistry):
        @asset(registry=registry)
        def source() -> int:
            return 42

        @asset(registry=registry, deps=["source"])
        def double(source: int) -> int:
            return source * 2

        result = materialize_with_observability(registry=registry)

        assert result.success is True
        assert result.execution_result.completed_count == 2
        assert result.execution_result.failed_count == 0

    def test_captures_logs(self, registry: AssetRegistry):
        import logging

        # Set the lattice logger level to ensure logs are captured
        logger = logging.getLogger("lattice")
        original_level = logger.level
        logger.setLevel(logging.INFO)

        try:

            @asset(registry=registry)
            def logging_asset() -> int:
                logger = logging.getLogger("lattice")
                logger.info("This is a log message")
                return 42

            result = materialize_with_observability(registry=registry)

            # Should have captured some logs
            assert len(result.logs) > 0
        finally:
            logger.setLevel(original_level)

    def test_tracks_lineage(self, registry: AssetRegistry):
        @asset(registry=registry)
        def source() -> int:
            return 42

        @asset(registry=registry, deps=["source"])
        def transform(source: int) -> int:
            return source * 2

        result = materialize_with_observability(registry=registry)

        # Should have lineage events for reads and writes
        assert len(result.lineage) > 0

        # Check for expected event types
        event_types = {e.event_type for e in result.lineage}
        assert "read" in event_types
        assert "write" in event_types

    def test_runs_checks(self, registry: AssetRegistry):
        from lattice.observability.checks import CheckDefinition

        check_registry = CheckRegistry()

        @asset(registry=registry)
        def my_data() -> dict:
            return {"value": 42}

        # Register check directly in our test registry
        def value_positive(data: dict) -> bool:
            return data["value"] > 0

        check_registry.register(
            CheckDefinition(
                name="value_positive",
                asset_key=my_data.key,
                fn=value_positive,
            )
        )

        result = materialize_with_observability(
            registry=registry,
            check_registry=check_registry,
        )

        assert len(result.check_results) == 1
        assert result.check_results[0].passed is True
        assert result.check_results[0].check_name == "value_positive"

    def test_check_failure(self, registry: AssetRegistry):
        from lattice.observability.checks import CheckDefinition

        check_registry = CheckRegistry()

        @asset(registry=registry)
        def my_data() -> dict:
            return {"value": -5}

        def value_positive(data: dict) -> bool:
            return data["value"] > 0

        check_registry.register(
            CheckDefinition(
                name="value_positive",
                asset_key=my_data.key,
                fn=value_positive,
            )
        )

        result = materialize_with_observability(
            registry=registry,
            check_registry=check_registry,
        )

        assert len(result.check_results) == 1
        assert result.check_results[0].passed is False
        assert result.check_results[0].status == CheckStatus.FAILED

    def test_saves_to_history_store(self, registry: AssetRegistry):
        store = SQLiteRunHistoryStore(":memory:")

        @asset(registry=registry)
        def my_asset() -> int:
            return 42

        result = materialize_with_observability(
            registry=registry,
            history_store=store,
        )

        runs = store.list_runs()
        assert len(runs) == 1
        assert runs[0].run_id == result.run_id

    def test_history_store_records_target(self, registry: AssetRegistry):
        store = SQLiteRunHistoryStore(":memory:")

        @asset(registry=registry)
        def source() -> int:
            return 42

        @asset(registry=registry, deps=["source"])
        def target(source: int) -> int:
            return source * 2

        materialize_with_observability(
            registry=registry,
            target="target",
            history_store=store,
        )

        runs = store.list_runs()
        assert runs[0].target == "target"

    def test_custom_io_manager(self, registry: AssetRegistry):
        io_manager = MemoryIOManager()

        @asset(registry=registry)
        def my_asset() -> int:
            return 42

        materialize_with_observability(
            registry=registry,
            io_manager=io_manager,
        )

        # Verify data was stored in our custom IO manager
        assert io_manager.has(AssetKey(name="my_asset"))
        assert io_manager.load(AssetKey(name="my_asset")) == 42

    def test_failed_execution(self, registry: AssetRegistry):
        @asset(registry=registry)
        def failing_asset() -> int:
            raise ValueError("Intentional failure")

        result = materialize_with_observability(registry=registry)

        assert result.success is False
        assert result.execution_result.failed_count == 1

    def test_multiple_checks_on_same_asset(self, registry: AssetRegistry):
        from lattice.observability.checks import CheckDefinition

        check_registry = CheckRegistry()

        @asset(registry=registry)
        def my_data() -> dict:
            return {"value": 42, "name": "test"}

        def value_positive(data: dict) -> bool:
            return data["value"] > 0

        def name_not_empty(data: dict) -> bool:
            return len(data["name"]) > 0

        check_registry.register(
            CheckDefinition(
                name="value_positive",
                asset_key=my_data.key,
                fn=value_positive,
            )
        )
        check_registry.register(
            CheckDefinition(
                name="name_not_empty",
                asset_key=my_data.key,
                fn=name_not_empty,
            )
        )

        result = materialize_with_observability(
            registry=registry,
            check_registry=check_registry,
        )

        assert len(result.check_results) == 2
        assert all(c.passed for c in result.check_results)

    def test_lineage_source_asset_tracking(self, registry: AssetRegistry):
        @asset(registry=registry)
        def source() -> int:
            return 42

        @asset(registry=registry, deps=["source"])
        def transform(source: int) -> int:
            return source * 2

        result = materialize_with_observability(registry=registry)

        # Find the read event for source during transform execution
        read_events = [e for e in result.lineage if e.event_type == "read"]
        assert len(read_events) >= 1

        # The read of 'source' should have 'transform' as the source_asset
        source_read = next(
            (e for e in read_events if e.asset_key.name == "source"),
            None,
        )
        assert source_read is not None
        assert source_read.source_asset.name == "transform"


class TestEndToEndWorkflow:
    """End-to-end workflow tests."""

    def test_full_workflow(self, registry: AssetRegistry):
        """Test a complete workflow with all observability features."""
        import logging

        from lattice.observability.checks import CheckDefinition

        check_registry = CheckRegistry()
        history_store = SQLiteRunHistoryStore(":memory:")

        # Ensure logging is configured at INFO level
        logger = logging.getLogger("lattice")
        original_level = logger.level
        logger.setLevel(logging.INFO)

        try:

            @asset(registry=registry)
            def raw_data() -> list:
                return [1, 2, 3, 4, 5]

            @asset(registry=registry, deps=["raw_data"])
            def processed(raw_data: list) -> list:
                return [x * 2 for x in raw_data]

            @asset(registry=registry, deps=["processed"])
            def summary(processed: list) -> dict:
                return {"sum": sum(processed), "count": len(processed)}

            def sum_positive(data: dict) -> bool:
                return data["sum"] > 0

            def count_valid(data: dict) -> bool:
                return data["count"] == 5

            check_registry.register(
                CheckDefinition(
                    name="sum_positive",
                    asset_key=summary.key,
                    fn=sum_positive,
                )
            )
            check_registry.register(
                CheckDefinition(
                    name="count_valid",
                    asset_key=summary.key,
                    fn=count_valid,
                )
            )

            # Execute with full observability
            result = materialize_with_observability(
                registry=registry,
                check_registry=check_registry,
                history_store=history_store,
            )

            # Verify execution
            assert result.success is True
            assert result.execution_result.completed_count == 3

            # Verify logs were captured
            assert len(result.logs) > 0

            # Verify lineage was tracked
            assert len(result.lineage) > 0
            write_events = [e for e in result.lineage if e.event_type == "write"]
            assert len(write_events) == 3  # One for each asset

            # Verify checks passed
            assert len(result.check_results) == 2
            assert all(c.passed for c in result.check_results)

            # Verify history was saved
            runs = history_store.list_runs()
            assert len(runs) == 1
            assert runs[0].run_id == result.run_id
            assert runs[0].completed_count == 3
        finally:
            logger.setLevel(original_level)
