"""
The @asset decorator for defining data assets.

This module provides the primary API for declaring assets in Lattice.
Dependencies are declared explicitly via the ``deps`` parameter as a
sequence of ``AssetKey`` or string shorthand.  When ``deps`` is omitted
(or ``None``), the asset is treated as a source asset with zero
dependencies.

The decorator returns an AssetWithChecks wrapper that enables the .check()
decorator for attaching data quality checks to assets.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, ParamSpec, TypeVar, overload

from lattice.asset.helpers import (
    _create_async_wrapper,
    _create_sync_wrapper,
    _extract_dependencies,
    _extract_return_type,
    _get_asset_params,
)
from lattice.models import AssetDefinition, AssetKey
from lattice.registry import AssetRegistry, get_global_registry

# TYPE_CHECKING block for imports only needed by type checkers (mypy, pyright).
# AssetWithChecks is imported here to avoid circular imports at runtime:
# observability/checks.py imports from this module, and this module uses
# AssetWithChecks only in type annotations (not at runtime), so we defer the import.
if TYPE_CHECKING:
    from typing import Any

    from lattice.observability.checks import AssetWithChecks

logger = logging.getLogger(__name__)

# Type variables for preserving function signatures through the decorator.
# P captures all parameters (names, types, defaults); R captures the return type.
P = ParamSpec("P")
R = TypeVar("R")


def _asset_decorator(
    func: Callable[P, R],
    key: AssetKey | None,
    deps: Sequence[AssetKey | str] | None,
    description: str | None,
    target_registry: AssetRegistry,
) -> AssetWithChecks:
    """Register a function as an asset and return an AssetWithChecks wrapper.

    Extracts dependencies, return type, and description from the function,
    wraps it to preserve async/sync nature, and registers the resulting
    ``AssetDefinition`` in the target registry.

    Parameters
    ----------
    func : Callable[P, R]
        The asset function to register.
    key : AssetKey or None
        Explicit asset key. Defaults to the function's ``__name__``.
    deps : Sequence[AssetKey | str] or None
        Explicit dependency list.  ``None`` means source asset (zero deps).
    description : str or None
        Optional description. Falls back to the function's docstring.
    target_registry : AssetRegistry
        The registry to register the asset definition in.

    Returns
    -------
    AssetWithChecks
        A wrapper around the registered ``AssetDefinition``.

    Raises
    ------
    TypeError
        If the number of declared dependencies does not match the number
        of non-skipped function parameters.
    """
    # Import here to avoid circular imports
    from lattice.observability.checks import AssetWithChecks

    asset_key = key or AssetKey(name=func.__name__)
    dependencies = _extract_dependencies(deps)
    return_type = _extract_return_type(func)

    # Arity validation: when deps are provided, the count must match the
    # number of non-skipped parameters on the function.
    if dependencies:
        params = _get_asset_params(func)
        if len(dependencies) != len(params):
            raise TypeError(
                f"Asset '{asset_key}' declares {len(dependencies)} dependency(ies) "
                f"but its function accepts {len(params)} parameter(s). "
                f"deps={[str(d) for d in dependencies]}, params={list(params)}"
            )

    # Preserve the async nature of the wrapped function.
    # We use Callable[..., Any] for the wrapped function since we can't
    # easily express the dual sync/async nature in the type system.
    wrapped_fn: Callable[..., Any]
    if inspect.iscoroutinefunction(func):
        wrapped_fn = _create_async_wrapper(func)
    else:
        wrapped_fn = _create_sync_wrapper(func)

    asset_def = AssetDefinition(
        key=asset_key,
        fn=wrapped_fn,
        dependencies=dependencies,
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
    return AssetWithChecks(asset_def)


@overload
def asset(fn: Callable[P, R]) -> AssetWithChecks: ...


@overload
def asset(
    *,
    key: AssetKey | None = None,
    group: str | None = None,
    deps: Sequence[AssetKey | str] | None = None,
    registry: AssetRegistry | None = None,
    description: str | None = None,
) -> Callable[[Callable[P, R]], AssetWithChecks]: ...


def asset(
    fn: Callable[P, R] | None = None,
    *,
    key: AssetKey | None = None,
    group: str | None = None,
    deps: Sequence[AssetKey | str] | None = None,
    registry: AssetRegistry | None = None,
    description: str | None = None,
) -> AssetWithChecks | Callable[[Callable[P, R]], AssetWithChecks]:
    """
    Decorator to define a data asset.

    Can be used with or without arguments::

        @asset
        def my_source() -> pd.DataFrame:
            ...

        @asset(key=AssetKey(group="analytics", name="stats"))
        def my_stats() -> dict:
            ...

    Use the ``group`` shorthand to place the asset in a group when the
    asset name matches the function name::

        @asset(group="analytics", deps=["user_orders"])
        def daily_revenue(orders: list[dict]) -> dict:
            ...

    Declare dependencies explicitly via the ``deps`` parameter::

        @asset(deps=["raw_users"])
        def cleaned_users(raw_users: list[dict]) -> list[dict]:
            ...

        @asset(deps=[
            AssetKey(name="daily_revenue", group="analytics"),
            AssetKey(name="user_stats", group="analytics"),
        ])
        def dashboard(revenue: dict, stats: dict) -> dict:
            ...

    Parameters
    ----------
    fn : Callable[P, R] or None
        The asset function (when used without parentheses).
    key : AssetKey or None
        Optional explicit asset key. Defaults to function name.
        Cannot be combined with ``group``.
    group : str or None
        Shorthand for ``key=AssetKey(name=func.__name__, group=group)``.
        Cannot be combined with ``key``.
    deps : Sequence[AssetKey | str] or None
        Explicit list of upstream dependencies. Strings are converted to
        ``AssetKey(name=s)`` in the default group. When ``None`` (the
        default), the asset is treated as a source with zero dependencies.
    registry : AssetRegistry or None
        Optional registry to use. Defaults to global registry.
    description : str or None
        Optional description for the asset.

    Returns
    -------
    AssetWithChecks or Callable[[Callable[P, R]], AssetWithChecks]
        An AssetWithChecks wrapper (delegating to AssetDefinition) that
        enables the .check() decorator, or a decorator if called with arguments.
    """
    if key is not None and group is not None:
        raise ValueError(
            "Cannot specify both 'key' and 'group' on @asset — "
            "use 'key' for full control or 'group' as shorthand"
        )

    target_registry = get_global_registry() if registry is None else registry

    # Handle both @asset and @asset(...) syntax.
    # When used without parentheses (@asset), fn is the decorated function
    # itself, so we register it immediately.
    # When used with parentheses (@asset(key=..., deps=...)), fn is None and
    # Python expects a callable back that will receive the decorated function
    # on the next call — the lambda closes over the configuration arguments
    # and defers the actual registration to that second invocation.
    if fn is not None:
        return _asset_decorator(fn, key, deps, description, target_registry)

    # Resolve key from group shorthand at decoration time.  The lambda
    # captures `group` and builds the effective AssetKey once it knows
    # the decorated function's __name__.
    def _decorator(func: Callable[P, R]) -> AssetWithChecks:
        effective_key = key
        if effective_key is None and group is not None:
            effective_key = AssetKey(name=func.__name__, group=group)
        return _asset_decorator(func, effective_key, deps, description, target_registry)

    return _decorator
