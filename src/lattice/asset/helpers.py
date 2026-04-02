"""Helper functions for the @asset decorator.

This module contains the internal utility functions used during asset
registration: dependency normalization, parameter extraction, return type
extraction, and sync/async wrapper creation.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from functools import wraps
from typing import Any, get_type_hints

from lattice.models import AssetKey

# Parameters that are never treated as asset dependencies.
SKIP_PARAMS = frozenset({"self", "cls", "context", "partition_key"})


def _normalize_deps(deps: Sequence[AssetKey | str]) -> tuple[AssetKey, ...]:
    """Normalize a sequence of dependencies to a tuple of AssetKey.

    String entries are converted to ``AssetKey(name=s)`` in the default group.

    Parameters
    ----------
    deps : Sequence[AssetKey | str]
        Raw dependency declarations.

    Returns
    -------
    tuple of AssetKey
        Normalized dependency keys.
    """
    return tuple(AssetKey(name=d) if isinstance(d, str) else d for d in deps)


def _extract_dependencies(
    deps: Sequence[AssetKey | str] | None,
) -> tuple[AssetKey, ...]:
    """Extract asset dependencies from an explicit deps declaration.

    When ``deps`` is ``None`` the asset is a source asset with no
    dependencies.  When provided, the sequence is normalized and returned.

    Parameters
    ----------
    deps : Sequence[AssetKey | str] or None
        Explicit dependency list supplied by the user.

    Returns
    -------
    tuple of AssetKey
        Normalized dependency keys.
    """
    if deps is None:
        return ()
    return _normalize_deps(deps)


def _get_asset_params(fn: Callable[..., Any]) -> tuple[str, ...]:
    """Return non-skipped parameter names from a function signature.

    Parameters
    ----------
    fn : Callable[..., Any]
        The function to inspect.

    Returns
    -------
    tuple of str
        Parameter names excluding those in ``SKIP_PARAMS``.
    """
    sig = inspect.signature(fn)
    return tuple(p for p in sig.parameters if p not in SKIP_PARAMS)


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


def _create_async_wrapper(func: Callable[..., Any]) -> Callable[..., Any]:
    """Create an async wrapper that preserves the original function's metadata.

    Used by ``_asset_decorator`` to wrap async asset functions before they
    are stored in an ``AssetDefinition``. The wrapper applies
    ``@functools.wraps`` so that ``__name__``, ``__doc__``, and
    ``__module__`` propagate from the original coroutine function to the
    wrapper. This ensures that logging, error messages, and introspection
    within the executor and web UI continue to reference the user-defined
    function name rather than an anonymous wrapper.

    Parameters
    ----------
    func : Callable[..., Any]
        The async function to wrap. Must be a coroutine function.

    Returns
    -------
    Callable[..., Any]
        An async wrapper that awaits ``func`` and carries its metadata.
    """

    @wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        return await func(*args, **kwargs)

    return async_wrapper


def _create_sync_wrapper(func: Callable[..., Any]) -> Callable[..., Any]:
    """Create a sync wrapper that preserves the original function's metadata.

    Used by ``_asset_decorator`` to wrap synchronous asset functions before
    they are stored in an ``AssetDefinition``. The wrapper applies
    ``@functools.wraps`` so that ``__name__``, ``__doc__``, and
    ``__module__`` propagate from the original function to the wrapper.
    This ensures that logging, error messages, and introspection within
    the executor and web UI continue to reference the user-defined
    function name rather than an anonymous wrapper.

    Parameters
    ----------
    func : Callable[..., Any]
        The sync function to wrap. Must not be a coroutine function.

    Returns
    -------
    Callable[..., Any]
        A sync wrapper that delegates to ``func`` and carries its metadata.
    """

    @wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    return sync_wrapper
