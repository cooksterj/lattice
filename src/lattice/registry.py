"""Asset registry for storing and retrieving asset definitions."""

from collections.abc import Iterator

from lattice.models import AssetDefinition, AssetKey


class AssetRegistry:
    """Registry for storing asset definitions.

    Can be used as a global registry or instantiated for isolation (e.g., testing).
    """

    def __init__(self) -> None:
        self._assets: dict[AssetKey, AssetDefinition] = {}

    def register(self, asset: AssetDefinition) -> None:
        """Register an asset definition."""
        if asset.key in self._assets:
            raise ValueError(f"Asset {asset.key} is already registered")
        self._assets[asset.key] = asset

    def get(self, key: AssetKey | str) -> AssetDefinition:
        """Retrieve an asset by key."""
        if isinstance(key, str):
            key = AssetKey(name=key)
        if key not in self._assets:
            raise KeyError(f"Asset {key} not found")
        return self._assets[key]

    def __contains__(self, key: AssetKey | str) -> bool:
        if isinstance(key, str):
            key = AssetKey(name=key)
        return key in self._assets

    def __iter__(self) -> Iterator[AssetDefinition]:
        return iter(self._assets.values())

    def __len__(self) -> int:
        return len(self._assets)

    def clear(self) -> None:
        """Remove all registered assets."""
        self._assets.clear()


# Global registry instance
_global_registry = AssetRegistry()


def get_global_registry() -> AssetRegistry:
    """Get the global asset registry."""
    return _global_registry
