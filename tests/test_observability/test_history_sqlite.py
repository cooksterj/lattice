"""Tests for SQLite run history storage."""

from datetime import datetime

import pytest

from lattice.observability.history import SQLiteRunHistoryStore
from lattice.observability.models import RunRecord


@pytest.fixture
def store():
    """Create an in-memory SQLite store for testing."""
    return SQLiteRunHistoryStore(":memory:")


@pytest.fixture
def sample_record():
    """Create a sample run record."""
    now = datetime.now()
    return RunRecord(
        run_id="test123",
        started_at=now,
        completed_at=now,
        status="completed",
        duration_ms=100.0,
        total_assets=5,
        completed_count=5,
        failed_count=0,
        target="target_asset",
        partition_key="2024-01-15",
    )


class TestSQLiteRunHistoryStore:
    """Tests for SQLiteRunHistoryStore."""

    def test_save_and_get(self, store, sample_record):
        store.save(sample_record)
        retrieved = store.get(sample_record.run_id)

        assert retrieved is not None
        assert retrieved.run_id == sample_record.run_id
        assert retrieved.status == sample_record.status
        assert retrieved.total_assets == sample_record.total_assets
        assert retrieved.target == sample_record.target
        assert retrieved.partition_key == sample_record.partition_key

    def test_get_nonexistent(self, store):
        result = store.get("nonexistent")
        assert result is None

    def test_list_runs(self, store):
        now = datetime.now()
        for i in range(5):
            record = RunRecord(
                run_id=f"run{i}",
                started_at=now,
                completed_at=now,
                status="completed" if i % 2 == 0 else "failed",
                duration_ms=100.0,
                total_assets=1,
                completed_count=1 if i % 2 == 0 else 0,
                failed_count=0 if i % 2 == 0 else 1,
            )
            store.save(record)

        runs = store.list_runs()
        assert len(runs) == 5

    def test_list_runs_with_limit(self, store):
        now = datetime.now()
        for i in range(10):
            record = RunRecord(
                run_id=f"run{i}",
                started_at=now,
                completed_at=now,
                status="completed",
                duration_ms=100.0,
                total_assets=1,
                completed_count=1,
                failed_count=0,
            )
            store.save(record)

        runs = store.list_runs(limit=3)
        assert len(runs) == 3

    def test_list_runs_with_offset(self, store):
        now = datetime.now()
        for i in range(5):
            record = RunRecord(
                run_id=f"run{i}",
                started_at=now,
                completed_at=now,
                status="completed",
                duration_ms=100.0,
                total_assets=1,
                completed_count=1,
                failed_count=0,
            )
            store.save(record)

        runs = store.list_runs(limit=2, offset=2)
        assert len(runs) == 2

    def test_list_runs_with_status_filter(self, store):
        now = datetime.now()
        for i in range(5):
            record = RunRecord(
                run_id=f"run{i}",
                started_at=now,
                completed_at=now,
                status="completed" if i % 2 == 0 else "failed",
                duration_ms=100.0,
                total_assets=1,
                completed_count=1 if i % 2 == 0 else 0,
                failed_count=0 if i % 2 == 0 else 1,
            )
            store.save(record)

        completed_runs = store.list_runs(status="completed")
        assert len(completed_runs) == 3

        failed_runs = store.list_runs(status="failed")
        assert len(failed_runs) == 2

    def test_delete(self, store, sample_record):
        store.save(sample_record)
        assert store.get(sample_record.run_id) is not None

        deleted = store.delete(sample_record.run_id)
        assert deleted is True
        assert store.get(sample_record.run_id) is None

    def test_delete_nonexistent(self, store):
        deleted = store.delete("nonexistent")
        assert deleted is False

    def test_count(self, store):
        now = datetime.now()
        for i in range(5):
            record = RunRecord(
                run_id=f"run{i}",
                started_at=now,
                completed_at=now,
                status="completed" if i % 2 == 0 else "failed",
                duration_ms=100.0,
                total_assets=1,
                completed_count=1 if i % 2 == 0 else 0,
                failed_count=0 if i % 2 == 0 else 1,
            )
            store.save(record)

        assert store.count() == 5
        assert store.count(status="completed") == 3
        assert store.count(status="failed") == 2

    def test_clear(self, store):
        now = datetime.now()
        for i in range(3):
            record = RunRecord(
                run_id=f"run{i}",
                started_at=now,
                completed_at=now,
                status="completed",
                duration_ms=100.0,
                total_assets=1,
                completed_count=1,
                failed_count=0,
            )
            store.save(record)

        assert store.count() == 3
        deleted_count = store.clear()
        assert deleted_count == 3
        assert store.count() == 0

    def test_upsert(self, store, sample_record):
        store.save(sample_record)

        # Update the same record
        updated_record = RunRecord(
            run_id=sample_record.run_id,
            started_at=sample_record.started_at,
            completed_at=sample_record.completed_at,
            status="failed",
            duration_ms=200.0,
            total_assets=10,
            completed_count=8,
            failed_count=2,
        )
        store.save(updated_record)

        retrieved = store.get(sample_record.run_id)
        assert retrieved.status == "failed"
        assert retrieved.total_assets == 10

    def test_json_fields_preserved(self, store):
        now = datetime.now()
        record = RunRecord(
            run_id="json_test",
            started_at=now,
            completed_at=now,
            status="completed",
            duration_ms=100.0,
            total_assets=1,
            completed_count=1,
            failed_count=0,
            logs_json='[{"level": "INFO", "message": "Test"}]',
            check_results_json='[{"passed": true, "check_name": "test"}]',
            lineage_json='[{"event_type": "write", "asset_key": "test"}]',
            asset_results_json='[{"key": "test", "status": "completed"}]',
        )
        store.save(record)

        retrieved = store.get("json_test")
        assert retrieved.logs_json == '[{"level": "INFO", "message": "Test"}]'
        assert '"passed": true' in retrieved.check_results_json

    def test_empty_store(self, store):
        runs = store.list_runs()
        assert runs == []
        assert store.count() == 0
