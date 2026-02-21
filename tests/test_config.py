"""Tests for lattice.config environment variable configuration."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from lattice.config import get_db_path, get_host, get_max_concurrency, get_port


class TestGetHost:
    def test_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert get_host() == "127.0.0.1"

    def test_env_override(self) -> None:
        with patch.dict(os.environ, {"LATTICE_HOST": "0.0.0.0"}):
            assert get_host() == "0.0.0.0"


class TestGetPort:
    def test_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert get_port() == 8000

    def test_env_override(self) -> None:
        with patch.dict(os.environ, {"LATTICE_PORT": "9000"}):
            assert get_port() == 9000

    def test_invalid_value_raises(self) -> None:
        with (
            patch.dict(os.environ, {"LATTICE_PORT": "abc"}),
            pytest.raises(ValueError, match="LATTICE_PORT must be an integer"),
        ):
            get_port()


class TestGetDbPath:
    def test_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert get_db_path() == "lattice_runs.db"

    def test_env_override(self) -> None:
        with patch.dict(os.environ, {"LATTICE_DB_PATH": "/data/runs.db"}):
            assert get_db_path() == "/data/runs.db"


class TestGetMaxConcurrency:
    def test_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert get_max_concurrency() == 4

    def test_env_override(self) -> None:
        with patch.dict(os.environ, {"LATTICE_MAX_CONCURRENCY": "8"}):
            assert get_max_concurrency() == 8

    def test_invalid_value_raises(self) -> None:
        with (
            patch.dict(os.environ, {"LATTICE_MAX_CONCURRENCY": "xyz"}),
            pytest.raises(ValueError, match="LATTICE_MAX_CONCURRENCY must be an integer"),
        ):
            get_max_concurrency()


class TestServeEnvIntegration:
    """Verify that serve() reads env vars when explicit args are None."""

    def test_serve_uses_env_defaults(self) -> None:
        """serve() should use env vars as defaults."""
        from lattice.config import get_host, get_port

        with patch.dict(os.environ, {"LATTICE_HOST": "0.0.0.0", "LATTICE_PORT": "3000"}):
            assert get_host() == "0.0.0.0"
            assert get_port() == 3000


class TestSQLiteStoreEnvIntegration:
    """Verify that SQLiteRunHistoryStore uses LATTICE_DB_PATH."""

    def test_store_uses_env_db_path(self, tmp_path: pytest.TempPathFactory) -> None:
        db_file = str(tmp_path / "test.db")  # type: ignore[union-attr]
        with patch.dict(os.environ, {"LATTICE_DB_PATH": db_file}):
            from lattice.observability.history.sqlite import SQLiteRunHistoryStore

            store = SQLiteRunHistoryStore()
            assert store._db_path == db_file

    def test_store_explicit_path_overrides_env(self) -> None:
        with patch.dict(os.environ, {"LATTICE_DB_PATH": "/should/not/use"}):
            from lattice.observability.history.sqlite import SQLiteRunHistoryStore

            store = SQLiteRunHistoryStore(db_path=":memory:")
            assert store._db_path == ":memory:"
