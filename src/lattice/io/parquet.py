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

    def _key_to_path(self, key: AssetKey) -> Path:
        """
        Convert asset key to parquet file path.

        Parameters
        ----------
        key : AssetKey
            The asset key.

        Returns
        -------
        Path
            The file path for this asset.
        """
        group_dir = self.base_path / key.group
        group_dir.mkdir(exist_ok=True)
        return group_dir / f"{key.name}.parquet"

    def load(self, key: AssetKey, annotation: type[T] | None = None) -> T:
        """
        Load DataFrame from parquet file.

        Parameters
        ----------
        key : AssetKey
            The asset to load.
        annotation : type or None, optional
            Ignored for parquet storage.

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

        path = self._key_to_path(key)
        if not path.exists():
            logger.debug("Asset %s not found at %s", key, path)
            raise KeyError(f"Asset {key} not found at {path}")
        logger.debug("Loading asset %s from %s", key, path)
        return pl.read_parquet(path)  # type: ignore[return-value]

    def store(self, key: AssetKey, value: Any) -> None:
        """
        Store DataFrame to parquet file.

        Parameters
        ----------
        key : AssetKey
            The asset key to store under.
        value : pl.DataFrame
            The DataFrame to store.

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
        path = self._key_to_path(key)
        logger.debug("Storing asset %s to %s", key, path)
        value.write_parquet(path)

    def has(self, key: AssetKey) -> bool:
        """
        Check if parquet file exists.

        Parameters
        ----------
        key : AssetKey
            The asset to check.

        Returns
        -------
        bool
            True if the file exists.
        """
        return self._key_to_path(key).exists()

    def delete(self, key: AssetKey) -> None:
        """
        Delete parquet file.

        Parameters
        ----------
        key : AssetKey
            The asset to delete.
        """
        path = self._key_to_path(key)
        if path.exists():
            path.unlink()
