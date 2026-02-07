"""
Log capture utilities for Lattice observability.

This module provides tools to capture log entries during asset execution,
associating them with the assets that produced them.
"""

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime

from lattice.models import AssetKey
from lattice.observability.models import LogEntry


class ExecutionLogHandler(logging.Handler):
    """
    A logging handler that captures log entries during execution.

    Captured entries include the asset context when set, allowing
    logs to be associated with the asset that produced them.

    Attributes
    ----------
    entries : list of LogEntry
        The captured log entries.
    """

    def __init__(self, on_entry: Callable[[LogEntry], None] | None = None) -> None:
        """Initialize the handler with an empty entry list.

        Parameters
        ----------
        on_entry : callable or None
            Optional callback invoked synchronously for each captured log entry.
            Receives the LogEntry as its sole argument. The caller is responsible
            for bridging to async if needed.
        """
        super().__init__()
        self._entries: list[LogEntry] = []
        self._current_asset: AssetKey | None = None
        self._on_entry = on_entry

    def set_current_asset(self, key: AssetKey | None) -> None:
        """
        Set the currently executing asset.

        Parameters
        ----------
        key : AssetKey or None
            The asset currently being executed, or None if between assets.
        """
        self._current_asset = key

    def emit(self, record: logging.LogRecord) -> None:
        """
        Capture a log record.

        Parameters
        ----------
        record : logging.LogRecord
            The log record to capture.
        """
        entry = LogEntry(
            timestamp=datetime.fromtimestamp(record.created),
            level=record.levelname,
            logger_name=record.name,
            message=self.format(record),
            asset_key=self._current_asset,
        )
        self._entries.append(entry)
        if self._on_entry is not None:
            self._on_entry(entry)

    @property
    def entries(self) -> list[LogEntry]:
        """
        Get the captured log entries.

        Returns
        -------
        list of LogEntry
            All captured log entries.
        """
        return self._entries.copy()

    def clear(self) -> None:
        """Clear all captured entries."""
        self._entries.clear()
        self._current_asset = None


@contextmanager
def capture_logs(
    logger_name: str = "lattice",
    level: int = logging.DEBUG,
    on_entry: Callable[[LogEntry], None] | None = None,
) -> Generator[ExecutionLogHandler, None, None]:
    """
    Context manager to capture logs during execution.

    Temporarily attaches an ExecutionLogHandler to the specified logger
    to capture all log entries. The handler is removed when the context
    exits.

    Parameters
    ----------
    logger_name : str
        Name of the logger to capture from. Defaults to "lattice".
    level : int
        Minimum log level to capture. Defaults to DEBUG.
    on_entry : callable or None
        Optional callback invoked synchronously for each captured log entry.
        Forwarded to the underlying ExecutionLogHandler.

    Yields
    ------
    ExecutionLogHandler
        The handler capturing log entries. Access .entries for captured logs.

    Examples
    --------
    >>> with capture_logs() as handler:
    ...     # Execute assets...
    ...     pass
    >>> logs = handler.entries
    """
    logger = logging.getLogger(logger_name)
    handler = ExecutionLogHandler(on_entry=on_entry)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))

    # Store original level to restore later
    original_level = logger.level
    if logger.getEffectiveLevel() > level:
        logger.setLevel(level)

    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)
