"""File-based IO manager using pickle serialization."""

import pickle
from pathlib import Path
from typing import Any, TypeVar

from lattice.io.base import IOManager
from lattice.models import AssetKey

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

    def _key_to_path(self, key: AssetKey) -> Path:
        """
        Convert asset key to file path.

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
        return group_dir / f"{key.name}.pkl"

    def load(self, key: AssetKey, annotation: type[T] | None = None) -> T:
        """
        Load value from pickle file.

        Parameters
        ----------
        key : AssetKey
            The asset to load.
        annotation : type or None, optional
            Ignored for pickle storage.

        Returns
        -------
        T
            The deserialized value.

        Raises
        ------
        KeyError
            If the asset file does not exist.
        """
        path = self._key_to_path(key)
        if not path.exists():
            raise KeyError(f"Asset {key} not found at {path}")
        with path.open("rb") as f:
            return pickle.load(f)  # type: ignore[no-any-return]  # noqa: S301

    def store(self, key: AssetKey, value: Any) -> None:
        """
        Store value to pickle file.

        Parameters
        ----------
        key : AssetKey
            The asset key to store under.
        value : Any
            The value to serialize and store.
        """
        path = self._key_to_path(key)
        with path.open("wb") as f:
            pickle.dump(value, f)

    def has(self, key: AssetKey) -> bool:
        """
        Check if asset file exists.

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
        Delete asset file.

        Parameters
        ----------
        key : AssetKey
            The asset to delete.
        """
        path = self._key_to_path(key)
        if path.exists():
            path.unlink()
