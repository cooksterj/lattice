"""File-based IO manager using pickle serialization."""

import logging
import pickle
from pathlib import Path
from typing import Any, TypeVar

from lattice.io.base import IOManager
from lattice.models import AssetKey

logger = logging.getLogger(__name__)

T = TypeVar("T")


class FileIOManager(IOManager):
    """
    File-based storage using pickle serialization.

    Each asset is stored as a separate .pkl file in the base directory.
    Assets are organized into subdirectories by group.

    Parameters
    ----------
    base_path : Path or str
        Directory to store asset files. Will be created if it doesn't exist.
    """

    def __init__(self, base_path: Path | str) -> None:
        """
        Initialize with base storage path.

        Parameters
        ----------
        base_path : Path or str
            Directory to store asset files.
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _key_to_path(
        self,
        key: AssetKey,
        partition_key: str | None = None,
    ) -> Path:
        """
        Convert asset key to file path.

        Parameters
        ----------
        key : AssetKey
            The asset key.
        partition_key : str or None, optional
            Partition key for scoped storage.

        Returns
        -------
        Path
            The file path for this asset.
        """
        if partition_key is not None:
            parent = self.base_path / key.group / partition_key
        else:
            parent = self.base_path / key.group
        parent.mkdir(parents=True, exist_ok=True)
        return parent / f"{key.name}.pkl"

    def load(
        self,
        key: AssetKey,
        annotation: type[T] | None = None,
        *,
        partition_key: str | None = None,
    ) -> T:
        """
        Load value from pickle file.

        Parameters
        ----------
        key : AssetKey
            The asset to load.
        annotation : type or None, optional
            Ignored for pickle storage.
        partition_key : str or None, optional
            Partition key for scoped storage.

        Returns
        -------
        T
            The deserialized value.

        Raises
        ------
        KeyError
            If the asset file does not exist.
        """
        path = self._key_to_path(key, partition_key)
        if not path.exists():
            logger.debug("Asset %s not found at %s", key, path)
            raise KeyError(f"Asset {key} not found at {path}")
        logger.debug("Loading asset %s from %s", key, path)
        with path.open("rb") as f:
            return pickle.load(f)  # type: ignore[no-any-return]  # noqa: S301

    def store(
        self,
        key: AssetKey,
        value: Any,
        *,
        partition_key: str | None = None,
    ) -> None:
        """
        Store value to pickle file.

        Parameters
        ----------
        key : AssetKey
            The asset key to store under.
        value : Any
            The value to serialize and store.
        partition_key : str or None, optional
            Partition key for scoped storage.
        """
        path = self._key_to_path(key, partition_key)
        logger.debug("Storing asset %s to %s", key, path)
        with path.open("wb") as f:
            pickle.dump(value, f)

    def has(self, key: AssetKey, *, partition_key: str | None = None) -> bool:
        """
        Check if asset file exists.

        Parameters
        ----------
        key : AssetKey
            The asset to check.
        partition_key : str or None, optional
            Partition key for scoped storage.

        Returns
        -------
        bool
            True if the file exists.
        """
        return self._key_to_path(key, partition_key).exists()

    def delete(self, key: AssetKey, *, partition_key: str | None = None) -> None:
        """
        Delete asset file.

        Parameters
        ----------
        key : AssetKey
            The asset to delete.
        partition_key : str or None, optional
            Partition key for scoped storage.
        """
        path = self._key_to_path(key, partition_key)
        if path.exists():
            path.unlink()
