"""
Data lineage tracking for Lattice observability.

This module provides tools to track read and write events during asset
execution, enabling full data lineage visibility.
"""

from datetime import datetime
from typing import Any, TypeVar

from lattice.io.base import IOManager
from lattice.models import AssetKey
from lattice.observability.models import LineageEvent

T = TypeVar("T")


class LineageTracker:
    """
    Tracks read and write events during execution.

    Maintains a list of lineage events and the current asset context
    so that reads can be attributed to the asset that triggered them.

    Attributes
    ----------
    events : list of LineageEvent
        The recorded lineage events.
    """

    def __init__(self) -> None:
        """Initialize the tracker with an empty event list."""
        self._events: list[LineageEvent] = []
        self._current_asset: AssetKey | None = None

    def set_current_asset(self, key: AssetKey | None) -> None:
        """
        Set the currently executing asset.

        Parameters
        ----------
        key : AssetKey or None
            The asset currently being executed, or None if between assets.
        """
        self._current_asset = key

    def record_read(
        self,
        key: AssetKey,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Record a read event.

        Parameters
        ----------
        key : AssetKey
            The asset that was read.
        metadata : dict or None
            Optional metadata about the read operation.
        """
        event = LineageEvent(
            event_type="read",
            asset_key=key,
            timestamp=datetime.now(),
            source_asset=self._current_asset,
            metadata=metadata or {},
        )
        self._events.append(event)

    def record_write(
        self,
        key: AssetKey,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Record a write event.

        Parameters
        ----------
        key : AssetKey
            The asset that was written.
        metadata : dict or None
            Optional metadata about the write operation.
        """
        event = LineageEvent(
            event_type="write",
            asset_key=key,
            timestamp=datetime.now(),
            source_asset=self._current_asset,
            metadata=metadata or {},
        )
        self._events.append(event)

    @property
    def events(self) -> list[LineageEvent]:
        """
        Get the recorded lineage events.

        Returns
        -------
        list of LineageEvent
            All recorded lineage events.
        """
        return self._events.copy()

    def clear(self) -> None:
        """Clear all recorded events."""
        self._events.clear()
        self._current_asset = None


class LineageIOManager(IOManager):
    """
    IO manager wrapper that records lineage events.

    Wraps any IOManager to track all load (read) and store (write)
    operations for lineage tracking purposes.

    Parameters
    ----------
    wrapped : IOManager
        The underlying IO manager to wrap.
    tracker : LineageTracker
        The tracker to record events to.
    """

    def __init__(self, wrapped: IOManager, tracker: LineageTracker) -> None:
        """Initialize with wrapped manager and tracker."""
        self._wrapped = wrapped
        self._tracker = tracker

    def load(
        self,
        key: AssetKey,
        annotation: type[T] | None = None,
        *,
        partition_key: str | None = None,
    ) -> T:
        """
        Load an asset and record the read event.

        Parameters
        ----------
        key : AssetKey
            The asset to load.
        annotation : type or None
            Optional type hint for deserialization.
        partition_key : str or None, optional
            Partition key for scoped storage.

        Returns
        -------
        T
            The loaded asset value.
        """
        self._tracker.record_read(key)
        return self._wrapped.load(key, annotation, partition_key=partition_key)

    def store(
        self,
        key: AssetKey,
        value: Any,
        *,
        partition_key: str | None = None,
    ) -> None:
        """
        Store an asset and record the write event.

        Parameters
        ----------
        key : AssetKey
            The asset key to store under.
        value : Any
            The value to store.
        partition_key : str or None, optional
            Partition key for scoped storage.
        """
        self._wrapped.store(key, value, partition_key=partition_key)
        self._tracker.record_write(key)

    def has(self, key: AssetKey, *, partition_key: str | None = None) -> bool:
        """
        Check if an asset exists in the wrapped manager.

        Parameters
        ----------
        key : AssetKey
            The asset to check.
        partition_key : str or None, optional
            Partition key for scoped storage.

        Returns
        -------
        bool
            True if the asset exists.
        """
        return self._wrapped.has(key, partition_key=partition_key)

    def delete(self, key: AssetKey, *, partition_key: str | None = None) -> None:
        """
        Delete an asset from the wrapped manager.

        Parameters
        ----------
        key : AssetKey
            The asset to delete.
        partition_key : str or None, optional
            Partition key for scoped storage.
        """
        self._wrapped.delete(key, partition_key=partition_key)

    @property
    def tracker(self) -> LineageTracker:
        """Get the lineage tracker."""
        return self._tracker

    @property
    def wrapped(self) -> IOManager:
        """Get the wrapped IO manager."""
        return self._wrapped
