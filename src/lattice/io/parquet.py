"""Parquet IO manager for DataFrame storage.

This module provides storage for polars DataFrames using the Parquet format.
"""

import logging
from pathlib import Path
from typing import Any, TypeVar

from lattice.io.base import IOManager
from lattice.models import AssetKey

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ParquetIOManager(IOManager):
    """
    Parquet-based storage for polars DataFrames.

    Optimized for columnar data with efficient compression.

    Parameters
    ----------
    base_path : Path or str
        Directory to store parquet files. Will be created if it doesn't exist.

    Raises
    ------
    TypeError
        If attempting to store a non-DataFrame value.
    """

    def __init__(self, base_path: Path | str) -> None:
        """
        Initialize with base storage path.

        Parameters
        ----------
        base_path : Path or str
            Directory to store parquet files.
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _key_to_path(
        self,
        key: AssetKey,
        partition_key: str | None = None,
    ) -> Path:
        """
        Convert asset key to parquet file path.

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
        return parent / f"{key.name}.parquet"

    def load(
        self,
        key: AssetKey,
        annotation: type[T] | None = None,
        *,
        partition_key: str | None = None,
    ) -> T:
        """
        Load DataFrame from parquet file.

        Parameters
        ----------
        key : AssetKey
            The asset to load.
        annotation : type or None, optional
            Ignored for parquet storage.
        partition_key : str or None, optional
            Partition key for scoped storage.

        Returns
        -------
        pl.DataFrame
            The loaded DataFrame.

        Raises
        ------
        KeyError
            If the parquet file does not exist.
        """
        import polars as pl

        path = self._key_to_path(key, partition_key)
        if not path.exists():
            logger.debug("Asset %s not found at %s", key, path)
            raise KeyError(f"Asset {key} not found at {path}")
        logger.debug("Loading asset %s from %s", key, path)
        return pl.read_parquet(path)  # type: ignore[return-value]

    def store(
        self,
        key: AssetKey,
        value: Any,
        *,
        partition_key: str | None = None,
    ) -> None:
        """
        Store DataFrame to parquet file.

        Parameters
        ----------
        key : AssetKey
            The asset key to store under.
        value : pl.DataFrame
            The DataFrame to store.
        partition_key : str or None, optional
            Partition key for scoped storage.

        Raises
        ------
        TypeError
            If value is not a polars DataFrame.
        """
        import polars as pl

        if not isinstance(value, pl.DataFrame):
            raise TypeError(
                f"ParquetIOManager can only store DataFrames, got {type(value).__name__}"
            )
        path = self._key_to_path(key, partition_key)
        logger.debug("Storing asset %s to %s", key, path)
        value.write_parquet(path)

    def has(self, key: AssetKey, *, partition_key: str | None = None) -> bool:
        """
        Check if parquet file exists.

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
        Delete parquet file.

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
