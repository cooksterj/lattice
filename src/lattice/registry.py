"""Asset registry for storing and retrieving asset definitions."""

from collections.abc import Iterator

from lattice.models import AssetDefinition, AssetKey


class AssetRegistry:
    """
    Registry for storing asset definitions.

    Can be used as a global registry or instantiated for isolation (e.g., testing).
    """

    def __init__(self) -> None:
        """Initialize an empty asset registry."""
        self._assets: dict[AssetKey, AssetDefinition] = {}

    def register(self, asset: AssetDefinition) -> None:
        """
        Register an asset definition.

        Parameters
        ----------
        asset : AssetDefinition
            The asset definition to register.

        Raises
        ------
        ValueError
            If an asset with the same key is already registered.
        """
        if asset.key in self._assets:
            raise ValueError(f"Asset {asset.key} is already registered")
        self._assets[asset.key] = asset

    def get(self, key: AssetKey | str) -> AssetDefinition:
        """
        Retrieve an asset by key.

        Parameters
        ----------
        key : AssetKey or str
            The key of the asset to retrieve. If a string is provided,
            it will be converted to an AssetKey.

        Returns
        -------
        AssetDefinition
            The registered asset definition.

        Raises
        ------
        KeyError
            If no asset with the given key is found.
        """
        if isinstance(key, str):
            key = AssetKey(name=key)
        if key not in self._assets:
            raise KeyError(f"Asset {key} not found")
        return self._assets[key]

    def __contains__(self, key: AssetKey | str) -> bool:
        """
        Check if an asset is registered.

        Parameters
        ----------
        key : AssetKey or str
            The key to check.

        Returns
        -------
        bool
            True if the asset is registered, False otherwise.
        """
        if isinstance(key, str):
            key = AssetKey(name=key)
        return key in self._assets

    def __iter__(self) -> Iterator[AssetDefinition]:
        """
        Iterate over registered asset definitions.

        Yields
        ------
        AssetDefinition
            Each registered asset definition.
        """
        return iter(self._assets.values())

    def __len__(self) -> int:
        """
        Return the number of registered assets.

        Returns
        -------
        int
            The count of registered assets.
        """
        return len(self._assets)

    def clear(self) -> None:
        """Remove all registered assets from the registry."""
        self._assets.clear()


# Global registry instance
_global_registry = AssetRegistry()


def get_global_registry() -> AssetRegistry:
    """
    Get the global asset registry.

    Returns
    -------
    AssetRegistry
        The singleton global registry instance.
    """
    return _global_registry
