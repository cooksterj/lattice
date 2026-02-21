"""Environment variable configuration for container-friendly operation.

Reads ``LATTICE_*`` environment variables with sensible defaults so that
Lattice can be configured externally (e.g. in Docker, ECS, EC2) without
modifying code.

Environment Variables
---------------------
LATTICE_HOST : str
    Bind address for the web server.  Default ``127.0.0.1``.
LATTICE_PORT : int
    Web server port.  Default ``8000``.
LATTICE_DB_PATH : str
    Path to the SQLite run-history database.  Default ``data/lattice_runs.db``.
LATTICE_MAX_CONCURRENCY : int
    Maximum number of concurrent asset executions in the
    :class:`~lattice.executor.AsyncExecutor`.  Default ``4``.
LATTICE_LOGGING_CONFIG : str
    Path to a custom logging configuration file (INI format).
"""

from __future__ import annotations

import os


def get_host() -> str:
    """Return the configured host, defaulting to ``127.0.0.1``."""
    return os.environ.get("LATTICE_HOST", "127.0.0.1")


def get_port() -> int:
    """Return the configured port, defaulting to ``8000``.

    Raises
    ------
    ValueError
        If ``LATTICE_PORT`` is set to a non-integer value.
    """
    raw = os.environ.get("LATTICE_PORT")
    if raw is None:
        return 8000
    try:
        return int(raw)
    except ValueError:
        msg = f"LATTICE_PORT must be an integer, got {raw!r}"
        raise ValueError(msg) from None


def get_db_path() -> str:
    """Return the configured database path, defaulting to ``data/lattice_runs.db``."""
    return os.environ.get("LATTICE_DB_PATH", "data/lattice_runs.db")


def get_max_concurrency() -> int:
    """Return the configured max concurrency, defaulting to ``4``.

    Raises
    ------
    ValueError
        If ``LATTICE_MAX_CONCURRENCY`` is set to a non-integer value.
    """
    raw = os.environ.get("LATTICE_MAX_CONCURRENCY")
    if raw is None:
        return 4
    try:
        return int(raw)
    except ValueError:
        msg = f"LATTICE_MAX_CONCURRENCY must be an integer, got {raw!r}"
        raise ValueError(msg) from None
