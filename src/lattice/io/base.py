"""Abstract base class for IO managers."""

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from lattice.models import AssetKey

T = TypeVar("T")


class IOManager(ABC):
    """
    Abstract base class for asset storage backends.

    IO managers handle loading previously materialized assets and
    storing newly computed asset values. Implementations can use
    in-memory storage, file systems, cloud storage, databases, etc.
    """

    @abstractmethod
    def load(
        self,
        key: AssetKey,
        annotation: type[T] | None = None,
        *,
        partition_key: str | None = None,
    ) -> T:
        """
        Load a previously stored asset value.

        Parameters
        ----------
        key : AssetKey
            The asset to load.
        annotation : type or None, optional
            The expected return type hint. Some IO managers may use this
            for type-aware deserialization.
        partition_key : str or None, optional
            Partition key for scoped storage (e.g. a date string).

        Returns
        -------
        T
            The stored asset value.

        Raises
        ------
        KeyError
            If the asset has not been materialized.
        """
        ...

    @abstractmethod
    def store(
        self,
        key: AssetKey,
        value: Any,
        *,
        partition_key: str | None = None,
    ) -> None:
        """
        Store an asset value.

        Parameters
        ----------
        key : AssetKey
            The asset key to store under.
        value : Any
            The value to store.
        partition_key : str or None, optional
            Partition key for scoped storage (e.g. a date string).
        """
        ...

    @abstractmethod
    def has(self, key: AssetKey, *, partition_key: str | None = None) -> bool:
        """
        Check if an asset has been materialized.

        Parameters
        ----------
        key : AssetKey
            The asset to check.
        partition_key : str or None, optional
            Partition key for scoped storage (e.g. a date string).

        Returns
        -------
        bool
            True if the asset exists in storage.
        """
        ...

    def delete(self, key: AssetKey, *, partition_key: str | None = None) -> None:
        """
        Delete a stored asset.

        This is an optional operation. The default implementation raises
        NotImplementedError. Subclasses may override to support deletion.

        Parameters
        ----------
        key : AssetKey
            The asset to delete.
        partition_key : str or None, optional
            Partition key for scoped storage (e.g. a date string).

        Raises
        ------
        NotImplementedError
            If the IO manager does not support deletion.
        """
        raise NotImplementedError("This IO manager does not support deletion")
