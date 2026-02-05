"""Tests for observability models."""

import json
from datetime import datetime

from lattice import AssetKey
from lattice.executor import AssetExecutionResult, AssetStatus, ExecutionResult
from lattice.observability.models import (
    CheckResult,
    CheckStatus,
    LineageEvent,
    LogEntry,
    RunRecord,
    RunResult,
)


class TestCheckResult:
    """Tests for CheckResult model."""

    def test_check_result_passed(self):
        result = CheckResult(
            passed=True,
            check_name="test_check",
            asset_key=AssetKey(name="test_asset"),
            status=CheckStatus.PASSED,
        )
        assert result.passed is True
        assert result.check_name == "test_check"
        assert result.status == CheckStatus.PASSED

    def test_check_result_failed(self):
        result = CheckResult(
            passed=False,
            check_name="test_check",
            asset_key=AssetKey(name="test_asset"),
            status=CheckStatus.FAILED,
            error="Validation failed",
        )
        assert result.passed is False
        assert result.error == "Validation failed"

    def test_check_result_with_metadata(self):
        result = CheckResult(
            passed=True,
            check_name="test_check",
            asset_key=AssetKey(name="test_asset"),
            status=CheckStatus.PASSED,
            metadata={"rows": 100, "nulls": 0},
            duration_ms=15.5,
        )
        assert result.metadata["rows"] == 100
        assert result.duration_ms == 15.5


class TestLogEntry:
    """Tests for LogEntry model."""

    def test_log_entry_creation(self):
        now = datetime.now()
        entry = LogEntry(
            timestamp=now,
            level="INFO",
            logger_name="lattice.executor",
            message="Executing asset",
            asset_key=AssetKey(name="my_asset"),
        )
        assert entry.timestamp == now
        assert entry.level == "INFO"
        assert entry.asset_key.name == "my_asset"

    def test_log_entry_without_asset(self):
        entry = LogEntry(
            timestamp=datetime.now(),
            level="DEBUG",
            logger_name="lattice",
            message="Starting execution",
        )
        assert entry.asset_key is None


class TestLineageEvent:
    """Tests for LineageEvent model."""

    def test_read_event(self):
        event = LineageEvent(
            event_type="read",
            asset_key=AssetKey(name="source_data"),
            timestamp=datetime.now(),
            source_asset=AssetKey(name="transform"),
        )
        assert event.event_type == "read"
        assert event.source_asset.name == "transform"

    def test_write_event(self):
        event = LineageEvent(
            event_type="write",
            asset_key=AssetKey(name="output"),
            timestamp=datetime.now(),
            metadata={"bytes": 1024},
        )
        assert event.event_type == "write"
        assert event.metadata["bytes"] == 1024


class TestRunResult:
    """Tests for RunResult model."""

    def test_run_result_properties(self):
        exec_result = ExecutionResult(
            run_id="abc123",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            status=AssetStatus.COMPLETED,
            asset_results=(),
            total_assets=5,
            completed_count=5,
            failed_count=0,
            duration_ms=100.0,
        )
        run_result = RunResult(execution_result=exec_result)

        assert run_result.run_id == "abc123"
        assert run_result.status == "completed"
        assert run_result.success is True

    def test_run_result_with_observability_data(self):
        exec_result = ExecutionResult(
            run_id="abc123",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            status=AssetStatus.COMPLETED,
            asset_results=(),
            total_assets=1,
            completed_count=1,
            failed_count=0,
            duration_ms=50.0,
        )
        log = LogEntry(
            timestamp=datetime.now(),
            level="INFO",
            logger_name="lattice",
            message="Test",
        )
        lineage = LineageEvent(
            event_type="write",
            asset_key=AssetKey(name="test"),
            timestamp=datetime.now(),
        )
        check = CheckResult(
            passed=True,
            check_name="test_check",
            asset_key=AssetKey(name="test"),
            status=CheckStatus.PASSED,
        )

        run_result = RunResult(
            execution_result=exec_result,
            logs=(log,),
            lineage=(lineage,),
            check_results=(check,),
        )

        assert len(run_result.logs) == 1
        assert len(run_result.lineage) == 1
        assert len(run_result.check_results) == 1


class TestRunRecord:
    """Tests for RunRecord model."""

    def test_run_record_creation(self):
        now = datetime.now()
        record = RunRecord(
            run_id="test123",
            started_at=now,
            completed_at=now,
            status="completed",
            duration_ms=100.0,
            total_assets=3,
            completed_count=3,
            failed_count=0,
        )
        assert record.run_id == "test123"
        assert record.status == "completed"

    def test_run_record_from_run_result(self):
        now = datetime.now()
        asset_result = AssetExecutionResult(
            key=AssetKey(name="test_asset"),
            status=AssetStatus.COMPLETED,
            started_at=now,
            completed_at=now,
            duration_ms=50.0,
        )
        exec_result = ExecutionResult(
            run_id="abc123",
            started_at=now,
            completed_at=now,
            status=AssetStatus.COMPLETED,
            asset_results=(asset_result,),
            total_assets=1,
            completed_count=1,
            failed_count=0,
            duration_ms=50.0,
        )
        log = LogEntry(
            timestamp=now,
            level="INFO",
            logger_name="lattice",
            message="Test log",
            asset_key=AssetKey(name="test_asset"),
        )
        check = CheckResult(
            passed=True,
            check_name="check1",
            asset_key=AssetKey(name="test_asset"),
            status=CheckStatus.PASSED,
            duration_ms=5.0,
        )
        run_result = RunResult(
            execution_result=exec_result,
            logs=(log,),
            check_results=(check,),
        )

        record = RunRecord.from_run_result(
            run_result,
            target="test_asset",
            partition_key="2024-01-15",
        )

        assert record.run_id == "abc123"
        assert record.target == "test_asset"
        assert record.partition_key == "2024-01-15"

        # Verify JSON serialization
        logs = json.loads(record.logs_json)
        assert len(logs) == 1
        assert logs[0]["message"] == "Test log"

        checks = json.loads(record.check_results_json)
        assert len(checks) == 1
        assert checks[0]["check_name"] == "check1"

        assets = json.loads(record.asset_results_json)
        assert len(assets) == 1
        assert assets[0]["key"] == "test_asset"
