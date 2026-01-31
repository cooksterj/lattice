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
        self._storage: dict[AssetKey, Any] = {}

    def load(self, key: AssetKey, annotation: type[T] | None = None) -> T:
        """
        Load value from memory.

        Parameters
        ----------
        key : AssetKey
            The asset to load.
        annotation : type or None, optional
            Ignored for memory storage.

        Returns
        -------
        T
            The stored value.

        Raises
        ------
        KeyError
            If the asset has not been stored.
        """
        if key not in self._storage:
            logger.debug("Asset %s not found in memory storage", key)
            raise KeyError(f"Asset {key} not found in memory storage")
        logger.debug("Loading asset %s from memory", key)
        return self._storage[key]  # type: ignore[no-any-return]

    def store(self, key: AssetKey, value: Any) -> None:
        """
        Store value in memory.

        Parameters
        ----------
        key : AssetKey
            The asset key to store under.
        value : Any
            The value to store.
        """
        logger.debug("Storing asset %s to memory", key)
        self._storage[key] = value

    def has(self, key: AssetKey) -> bool:
        """
        Check if asset exists in memory.

        Parameters
        ----------
        key : AssetKey
            The asset to check.

        Returns
        -------
        bool
            True if the asset is stored.
        """
        return key in self._storage

    def delete(self, key: AssetKey) -> None:
        """
        Delete asset from memory.

        Parameters
        ----------
        key : AssetKey
            The asset to delete.
        """
        if key in self._storage:
            del self._storage[key]

    def clear(self) -> None:
        """Clear all stored values."""
        self._storage.clear()

    def __len__(self) -> int:
        """Return number of stored assets."""
        return len(self._storage)

    def __contains__(self, key: AssetKey) -> bool:
        """Support 'in' operator."""
        return self.has(key)
