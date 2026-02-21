"""SQLite-backed run history storage."""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from lattice.observability.history.base import RunHistoryStore
from lattice.observability.models import RunRecord

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms REAL,
    total_assets INTEGER,
    completed_count INTEGER,
    failed_count INTEGER,
    target TEXT,
    partition_key TEXT,
    logs_json TEXT,
    lineage_json TEXT,
    check_results_json TEXT,
    asset_results_json TEXT
)
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at DESC)
"""


class SQLiteRunHistoryStore(RunHistoryStore):
    """
    SQLite-backed run history storage.

    Stores run records in a SQLite database for persistent history.
    Supports in-memory databases for testing.

    Parameters
    ----------
    db_path : str or Path
        Path to the SQLite database file.
        Use ":memory:" for an in-memory database.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize the store and create tables if needed.

        Parameters
        ----------
        db_path : str, Path, or None
            Path to the SQLite database file.
            When *None*, reads ``LATTICE_DB_PATH`` env var (default
            ``lattice_runs.db``).  Use ``":memory:"`` for an in-memory
            database.
        """
        if db_path is None:
            from lattice.config import get_db_path

            db_path = get_db_path()
        self._db_path = str(db_path)
        self._is_memory = self._db_path == ":memory:"
        # For in-memory databases, keep a persistent connection
        self._conn: sqlite3.Connection | None = None
        if self._is_memory:
            self._conn = sqlite3.connect(":memory:")
        self._init_db()

    def _init_db(self) -> None:
        """Create the database tables if they don't exist."""
        with self._connection() as conn:
            conn.execute(CREATE_TABLE_SQL)
            conn.execute(CREATE_INDEX_SQL)
            conn.commit()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Get a database connection as a context manager.

        For in-memory databases, uses the persistent connection.
        For file-based databases, creates a new connection.

        Yields
        ------
        sqlite3.Connection
            A connection to the database.
        """
        if self._is_memory:
            assert self._conn is not None
            yield self._conn
        else:
            conn = sqlite3.connect(self._db_path)
            try:
                yield conn
            finally:
                conn.close()

    def save(self, record: RunRecord) -> None:
        """
        Save a run record.

        Parameters
        ----------
        record : RunRecord
            The run record to save.
        """
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, started_at, completed_at, status, duration_ms,
                    total_assets, completed_count, failed_count, target,
                    partition_key, logs_json, lineage_json, check_results_json,
                    asset_results_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.started_at.isoformat(),
                    record.completed_at.isoformat(),
                    record.status,
                    record.duration_ms,
                    record.total_assets,
                    record.completed_count,
                    record.failed_count,
                    record.target,
                    record.partition_key,
                    record.logs_json,
                    record.lineage_json,
                    record.check_results_json,
                    record.asset_results_json,
                ),
            )
            conn.commit()

    def get(self, run_id: str) -> RunRecord | None:
        """
        Get a run record by ID.

        Parameters
        ----------
        run_id : str
            The run ID to look up.

        Returns
        -------
        RunRecord or None
            The run record if found, None otherwise.
        """
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?",
                (run_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_record(row)

    def list_runs(
        self,
        limit: int = 50,
        status: str | None = None,
        offset: int = 0,
    ) -> list[RunRecord]:
        """
        List run records with optional filtering.

        Parameters
        ----------
        limit : int
            Maximum number of records to return.
        status : str or None
            Filter by status if provided.
        offset : int
            Number of records to skip for pagination.

        Returns
        -------
        list of RunRecord
            Matching run records, ordered by start time descending.
        """
        with self._connection() as conn:
            if status is not None:
                cursor = conn.execute(
                    """
                    SELECT * FROM runs
                    WHERE status = ?
                    ORDER BY started_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (status, limit, offset),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM runs
                    ORDER BY started_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
            return [self._row_to_record(row) for row in cursor.fetchall()]

    def delete(self, run_id: str) -> bool:
        """
        Delete a run record.

        Parameters
        ----------
        run_id : str
            The run ID to delete.

        Returns
        -------
        bool
            True if the record was deleted, False if not found.
        """
        with self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM runs WHERE run_id = ?",
                (run_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def count(self, status: str | None = None) -> int:
        """
        Count run records with optional status filter.

        Parameters
        ----------
        status : str or None
            Filter by status if provided.

        Returns
        -------
        int
            Number of matching records.
        """
        with self._connection() as conn:
            if status is not None:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM runs WHERE status = ?",
                    (status,),
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM runs")
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def clear(self) -> int:
        """
        Delete all run records.

        Returns
        -------
        int
            Number of records deleted.
        """
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM runs")
            conn.commit()
            return cursor.rowcount

    def _row_to_record(self, row: tuple[Any, ...]) -> RunRecord:
        """
        Convert a database row to a RunRecord.

        Parameters
        ----------
        row : tuple
            Database row from a SELECT query.

        Returns
        -------
        RunRecord
            The corresponding RunRecord.
        """
        return RunRecord(
            run_id=row[0],
            started_at=datetime.fromisoformat(row[1]),
            completed_at=datetime.fromisoformat(row[2]),
            status=row[3],
            duration_ms=row[4],
            total_assets=row[5],
            completed_count=row[6],
            failed_count=row[7],
            target=row[8],
            partition_key=row[9],
            logs_json=row[10] or "[]",
            lineage_json=row[11] or "[]",
            check_results_json=row[12] or "[]",
            asset_results_json=row[13] or "[]",
        )
