"""In-memory IO manager for testing and ephemeral pipelines."""

import logging
from typing import Any, TypeVar

from lattice.io.base import IOManager
from lattice.models import AssetKey

logger = logging.getLogger(__name__)

T = TypeVar("T")


class MemoryIOManager(IOManager):
    """
    In-memory storage for testing and ephemeral pipelines.

    Stores values in a dictionary that is lost when the process ends.
    Useful for testing, development, and pipelines that don't need
    persistence.
    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._storage: dict[tuple[AssetKey, str | None], Any] = {}

    def load(
        self,
        key: AssetKey,
        annotation: type[T] | None = None,
        *,
        partition_key: str | None = None,
    ) -> T:
        """
        Load value from memory.

        Parameters
        ----------
        key : AssetKey
            The asset to load.
        annotation : type or None, optional
            Ignored for memory storage.
        partition_key : str or None, optional
            Partition key for scoped storage.

        Returns
        -------
        T
            The stored value.

        Raises
        ------
        KeyError
            If the asset has not been stored.
        """
        composite = (key, partition_key)
        if composite not in self._storage:
            logger.debug("Asset %s not found in memory storage", key)
            raise KeyError(f"Asset {key} not found in memory storage")
        logger.debug("Loading asset %s from memory", key)
        return self._storage[composite]  # type: ignore[no-any-return]

    def store(
        self,
        key: AssetKey,
        value: Any,
        *,
        partition_key: str | None = None,
    ) -> None:
        """
        Store value in memory.

        Parameters
        ----------
        key : AssetKey
            The asset key to store under.
        value : Any
            The value to store.
        partition_key : str or None, optional
            Partition key for scoped storage.
        """
        logger.debug("Storing asset %s to memory", key)
        self._storage[(key, partition_key)] = value

    def has(self, key: AssetKey, *, partition_key: str | None = None) -> bool:
        """
        Check if asset exists in memory.

        Parameters
        ----------
        key : AssetKey
            The asset to check.
        partition_key : str or None, optional
            Partition key for scoped storage.

        Returns
        -------
        bool
            True if the asset is stored.
        """
        return (key, partition_key) in self._storage

    def delete(self, key: AssetKey, *, partition_key: str | None = None) -> None:
        """
        Delete asset from memory.

        Parameters
        ----------
        key : AssetKey
            The asset to delete.
        partition_key : str or None, optional
            Partition key for scoped storage.
        """
        composite = (key, partition_key)
        if composite in self._storage:
            del self._storage[composite]

    def clear(self) -> None:
        """Clear all stored values."""
        self._storage.clear()

    def __len__(self) -> int:
        """Return number of stored assets."""
        return len(self._storage)

    def __contains__(self, key: AssetKey) -> bool:
        """Support 'in' operator (checks unpartitioned slot)."""
        return self.has(key)
