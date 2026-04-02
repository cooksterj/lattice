"""Tests for the Lattice CLI."""

from datetime import datetime
from unittest.mock import patch

import pytest

from lattice.cli import cmd_delete, cmd_list, cmd_show, main
from lattice.observability.history import SQLiteRunHistoryStore
from lattice.observability.models import RunRecord


@pytest.fixture
def store():
    """Create an in-memory SQLite store for testing."""
    return SQLiteRunHistoryStore(":memory:")


@pytest.fixture
def sample_records(store):
    """Create sample run records in the store."""
    now = datetime.now()
    for i in range(3):
        record = RunRecord(
            run_id=f"run{i:04d}",
            started_at=now,
            completed_at=now,
            status="completed" if i % 2 == 0 else "failed",
            duration_ms=100.0 * (i + 1),
            total_assets=5,
            completed_count=5 if i % 2 == 0 else 3,
            failed_count=0 if i % 2 == 0 else 2,
            target="my_target" if i == 0 else None,
            partition_key=f"2024-01-{15 + i}",
            logs_json=(
                '[{"level": "INFO", "message": "Test log", "logger_name": "lattice", '
                '"timestamp": "2024-01-15T10:00:00", "asset_key": "test"}]'
            ),
            check_results_json=(
                '[{"passed": true, "check_name": "test_check", "asset_key": "test", '
                '"status": "passed", "duration_ms": 5.0}]'
            ),
            lineage_json=(
                '[{"event_type": "write", "asset_key": "test", '
                '"timestamp": "2024-01-15T10:00:00", "source_asset": null}]'
            ),
            asset_results_json='[{"key": "test", "status": "completed", "duration_ms": 50.0}]',
        )
        store.save(record)
    return store


class TestCmdList:
    """Tests for the list command."""

    def test_list_empty(self, store, capsys):
        class Args:
            db = None
            limit = 20
            status = None

        with patch("lattice.cli.cli.get_store", return_value=store):
            result = cmd_list(Args())

        assert result == 0
        captured = capsys.readouterr()
        assert "No runs found" in captured.out

    def test_list_runs(self, sample_records, capsys):
        class Args:
            db = None
            limit = 20
            status = None

        with patch("lattice.cli.cli.get_store", return_value=sample_records):
            result = cmd_list(Args())

        assert result == 0
        captured = capsys.readouterr()
        assert "run0000" in captured.out
        assert "run0001" in captured.out
        assert "run0002" in captured.out

    def test_list_with_status_filter(self, sample_records, capsys):
        class Args:
            db = None
            limit = 20
            status = "completed"

        with patch("lattice.cli.cli.get_store", return_value=sample_records):
            result = cmd_list(Args())

        assert result == 0
        captured = capsys.readouterr()
        assert "run0000" in captured.out
        assert "run0002" in captured.out
        # run0001 is failed, should not appear
        assert "run0001" not in captured.out

    def test_list_with_limit(self, sample_records, capsys):
        class Args:
            db = None
            limit = 1
            status = None

        with patch("lattice.cli.cli.get_store", return_value=sample_records):
            result = cmd_list(Args())

        assert result == 0
        captured = capsys.readouterr()
        # Only one run should be shown
        lines = [
            line
            for line in captured.out.strip().split("\n")
            if line and not line.startswith("-") and "Run ID" not in line
        ]
        assert len(lines) == 1


class TestCmdShow:
    """Tests for the show command."""

    def test_show_not_found(self, store, capsys):
        class Args:
            db = None
            run_id = "nonexistent"
            logs = False
            checks = False
            lineage = False
            assets = False
            all = False

        with patch("lattice.cli.cli.get_store", return_value=store):
            result = cmd_show(Args())

        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_show_basic(self, sample_records, capsys):
        class Args:
            db = None
            run_id = "run0000"
            logs = False
            checks = False
            lineage = False
            assets = False
            all = False

        with patch("lattice.cli.cli.get_store", return_value=sample_records):
            result = cmd_show(Args())

        assert result == 0
        captured = capsys.readouterr()
        assert "run0000" in captured.out
        assert "completed" in captured.out
        assert "my_target" in captured.out

    def test_show_with_logs(self, sample_records, capsys):
        class Args:
            db = None
            run_id = "run0000"
            logs = True
            checks = False
            lineage = False
            assets = False
            all = False

        with patch("lattice.cli.cli.get_store", return_value=sample_records):
            result = cmd_show(Args())

        assert result == 0
        captured = capsys.readouterr()
        assert "--- Logs ---" in captured.out
        assert "Test log" in captured.out

    def test_show_with_checks(self, sample_records, capsys):
        class Args:
            db = None
            run_id = "run0000"
            logs = False
            checks = True
            lineage = False
            assets = False
            all = False

        with patch("lattice.cli.cli.get_store", return_value=sample_records):
            result = cmd_show(Args())

        assert result == 0
        captured = capsys.readouterr()
        assert "--- Check Results ---" in captured.out
        assert "test_check" in captured.out

    def test_show_with_lineage(self, sample_records, capsys):
        class Args:
            db = None
            run_id = "run0000"
            logs = False
            checks = False
            lineage = True
            assets = False
            all = False

        with patch("lattice.cli.cli.get_store", return_value=sample_records):
            result = cmd_show(Args())

        assert result == 0
        captured = capsys.readouterr()
        assert "--- Lineage ---" in captured.out
        assert "write" in captured.out

    def test_show_with_assets(self, sample_records, capsys):
        class Args:
            db = None
            run_id = "run0000"
            logs = False
            checks = False
            lineage = False
            assets = True
            all = False

        with patch("lattice.cli.cli.get_store", return_value=sample_records):
            result = cmd_show(Args())

        assert result == 0
        captured = capsys.readouterr()
        assert "--- Asset Results ---" in captured.out
        assert "test" in captured.out

    def test_show_all(self, sample_records, capsys):
        class Args:
            db = None
            run_id = "run0000"
            logs = False
            checks = False
            lineage = False
            assets = False
            all = True

        with patch("lattice.cli.cli.get_store", return_value=sample_records):
            result = cmd_show(Args())

        assert result == 0
        captured = capsys.readouterr()
        assert "--- Logs ---" in captured.out
        assert "--- Check Results ---" in captured.out
        assert "--- Lineage ---" in captured.out
        assert "--- Asset Results ---" in captured.out


class TestCmdDelete:
    """Tests for the delete command."""

    def test_delete_success(self, sample_records, capsys):
        class Args:
            db = None
            run_id = "run0000"

        with patch("lattice.cli.cli.get_store", return_value=sample_records):
            result = cmd_delete(Args())

        assert result == 0
        captured = capsys.readouterr()
        assert "Deleted" in captured.out

        # Verify it's actually deleted
        assert sample_records.get("run0000") is None

    def test_delete_not_found(self, store, capsys):
        class Args:
            db = None
            run_id = "nonexistent"

        with patch("lattice.cli.cli.get_store", return_value=store):
            result = cmd_delete(Args())

        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out


class TestMain:
    """Tests for the main CLI entry point."""

    def test_no_command_shows_help(self, capsys):
        result = main([])
        assert result == 0
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower() or "Available commands" in captured.out

    def test_list_command(self, store, capsys):
        with patch("lattice.cli.cli.get_store", return_value=store):
            result = main(["list"])

        assert result == 0

    def test_show_command(self, store, capsys):
        with patch("lattice.cli.cli.get_store", return_value=store):
            result = main(["show", "test123"])

        # Will return 1 because run doesn't exist, but parsing worked
        assert result == 1

    def test_delete_command(self, store, capsys):
        with patch("lattice.cli.cli.get_store", return_value=store):
            result = main(["delete", "test123"])

        assert result == 1  # Not found

    def test_db_option(self, tmp_path, capsys):
        db_path = str(tmp_path / "test.db")
        result = main(["--db", db_path, "list"])
        assert result == 0
