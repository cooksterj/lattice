"""
The @asset decorator for defining data assets.

This module provides the primary API for declaring assets in Lattice.
The decorator automatically extracts dependencies from function parameter
names, captures return type annotations, and registers the asset definition
to a registry (global by default).
"""

import inspect
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar, get_type_hints, overload

from lattice.models import AssetDefinition, AssetKey
from lattice.registry import AssetRegistry, get_global_registry

logger = logging.getLogger(__name__)

# Type variables for preserving function signatures through the decorator.
# P captures all parameters (names, types, defaults); R captures the return type.
P = ParamSpec("P")
R = TypeVar("R")


def _extract_dependencies(
    fn: Callable[..., Any],
    explicit_deps: dict[str, AssetKey] | None = None,
) -> tuple[tuple[AssetKey, ...], tuple[str, ...]]:
    """
    Extract asset dependencies from the function signature.

    Each parameter name is treated as a dependency on an asset with that name,
    unless an explicit mapping is provided in explicit_deps.
    Special parameters (self, cls, context, partition_key) are excluded.

    Parameters
    ----------
    fn : Callable[..., Any]
        The function to extract dependencies from.
    explicit_deps : dict[str, AssetKey] or None
        Optional mapping of parameter names to asset keys. Use this for
        dependencies on assets in non-default groups.

    Returns
    -------
    tuple of (tuple of AssetKey, tuple of str)
        Asset keys for dependencies and their corresponding parameter names.
    """
    sig = inspect.signature(fn)
    deps: list[AssetKey] = []
    params: list[str] = []
    explicit_deps = explicit_deps or {}

    for param_name in sig.parameters:
        # Skip special parameters that aren't asset dependencies
        if param_name in ("self", "cls", "context", "partition_key"):
            continue
        # Use the explicit mapping if provided, otherwise derive from the parameter name
        if param_name in explicit_deps:
            deps.append(explicit_deps[param_name])
        else:
            deps.append(AssetKey(name=param_name))
        params.append(param_name)

    return tuple(deps), tuple(params)


def _extract_return_type(fn: Callable[..., Any]) -> type | None:
    """
    Extract return type annotation from a function.

    Parameters
    ----------
    fn : Callable[..., Any]
        The function to extract the return type from.

    Returns
    -------
    type or None
        The return type annotation, or None if not annotated or extraction fails.
    """
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
    deps: dict[str, AssetKey] | None = None,
    registry: AssetRegistry | None = None,
    description: str | None = None,
) -> Callable[[Callable[P, R]], AssetDefinition]: ...


def asset(
    fn: Callable[P, R] | None = None,
    *,
    key: AssetKey | None = None,
    deps: dict[str, AssetKey] | None = None,
    registry: AssetRegistry | None = None,
    description: str | None = None,
) -> AssetDefinition | Callable[[Callable[P, R]], AssetDefinition]:
    """
    Decorator to define a data asset.

    Can be used with or without arguments::

        @asset
        def my_asset() -> pd.DataFrame:
            ...

        @asset(key=AssetKey(group="analytics", name="stats"))
        def my_stats() -> dict:
            ...

    For dependencies on grouped assets, use the 'deps' parameter to map
    parameter names to asset keys::

        @asset(deps={
            "revenue": AssetKey(name="daily_revenue", group="analytics"),
            "stats": AssetKey(name="user_stats", group="analytics"),
        })
        def dashboard (revenue: dict, stats: dict) -> dict:
            ...

    Parameters
    ----------
    fn : Callable[P, R] or None
        The asset function (when used without parentheses).
    key : AssetKey or None
        Optional explicit asset key. Defaults to function name.
    deps : dict[str, AssetKey] or None
        Optional mapping of parameter names to asset keys. Use this when
        depending on assets in non-default groups. Parameters not in this
        dict are resolved by name in the default group.
    registry : AssetRegistry or None
        Optional registry to use. Defaults to global registry.
    description : str or None
        Optional description for the asset.

    Returns
    -------
    AssetDefinition or Callable[[Callable[P, R]], AssetDefinition]
        An AssetDefinition wrapping the function, or a decorator if called
        with arguments.
    """
    target_registry = get_global_registry() if registry is None else registry

    def decorator(func: Callable[P, R]) -> AssetDefinition:
        asset_key = key or AssetKey(name=func.__name__)
        dependencies, dependency_params = _extract_dependencies(func, deps)
        return_type = _extract_return_type(func)

        # Preserve the async nature of the wrapped function.
        # We use Callable[..., Any] for the wrapped function since we can't
        # easily express the dual sync/async nature in the type system.
        wrapped_fn: Callable[..., Any]
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await func(*args, **kwargs)

            wrapped_fn = async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                return func(*args, **kwargs)

            wrapped_fn = sync_wrapper

        asset_def = AssetDefinition(
            key=asset_key,
            fn=wrapped_fn,
            dependencies=dependencies,
            dependency_params=dependency_params,
            return_type=return_type,
            description=description or func.__doc__,
        )

        target_registry.register(asset_def)
        logger.info("Asset registered: %s", asset_key)
        logger.debug(
            "Asset %s depends on: %s",
            asset_key,
            [str(d) for d in dependencies] if dependencies else "none",
        )
        return asset_def

    # Handle both @asset and @asset(...) syntax
    if fn is not None:
        return decorator(fn)
    return decorator
