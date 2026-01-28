"""The @asset decorator for defining data assets."""

import inspect
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar, get_type_hints, overload

from lattice.models import AssetDefinition, AssetKey
from lattice.registry import AssetRegistry, get_global_registry

P = ParamSpec("P")
R = TypeVar("R")


def _extract_dependencies(fn: Callable[..., Any]) -> tuple[AssetKey, ...]:
    """Extract asset dependencies from the function signature.

    Each parameter name is treated as a dependency on an asset with that name.
    """
    sig = inspect.signature(fn)
    deps: list[AssetKey] = []

    for param_name in sig.parameters:
        # Skip special parameters that aren't asset dependencies
        if param_name in ("self", "cls", "context", "partition_key"):
            continue
        deps.append(AssetKey(name=param_name))

    return tuple(deps)


def _extract_return_type(fn: Callable[..., Any]) -> type | None:
    """Extract return type annotation from a function."""
    try:
        hints = get_type_hints(fn)
    except Exception:
        hints = {}
    return hints.get("return")


@overload
def asset(fn: Callable[P, R]) -> AssetDefinition: ...


@overload
def asset(
    *,
    key: AssetKey | None = None,
    registry: AssetRegistry | None = None,
    description: str | None = None,
) -> Callable[[Callable[P, R]], AssetDefinition]: ...


def asset(
    fn: Callable[P, R] | None = None,
    *,
    key: AssetKey | None = None,
    registry: AssetRegistry | None = None,
    description: str | None = None,
) -> AssetDefinition | Callable[[Callable[P, R]], AssetDefinition]:
    """Decorator to define a data asset.

    Can be used with or without arguments:

        @asset
        def my_asset() -> pd.DataFrame:
            ...

        @asset(key=AssetKey(group="analytics", name="stats"))
        def my_stats() -> dict:
            ...

    Args:
        fn: The asset function (when used without parentheses).
        key: Optional explicit asset key. Defaults to function name.
        registry: Optional registry to use. Defaults to global registry.
        description: Optional description for the asset.

    Returns:
        An AssetDefinition wrapping the function.
    """
    target_registry = get_global_registry() if registry is None else registry

    def decorator(func: Callable[P, R]) -> AssetDefinition:
        asset_key = key or AssetKey(name=func.__name__)
        dependencies = _extract_dependencies(func)
        return_type = _extract_return_type(func)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> R:
            return func(*args, **kwargs)

        asset_def = AssetDefinition(
            key=asset_key,
            fn=wrapper,
            dependencies=dependencies,
            return_type=return_type,
            description=description or func.__doc__,
        )

        target_registry.register(asset_def)
        return asset_def

    # Handle both @asset and @asset(...) syntax
    if fn is not None:
        return decorator(fn)
    return decorator
