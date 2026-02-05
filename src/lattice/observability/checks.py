"""
Data quality checks for Lattice observability.

This module provides a framework for defining and running data quality
checks on assets, with results tracked as part of observability.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from lattice.models import AssetDefinition, AssetKey
from lattice.observability.models import CheckResult, CheckStatus


class CheckDefinition(BaseModel):
    """
    Definition of a data quality check for an asset.

    Attributes
    ----------
    name : str
        Name of the check.
    asset_key : AssetKey
        The asset this check applies to.
    fn : Callable
        The check function. Should accept the asset value and return
        a CheckResult or bool.
    description : str or None
        Optional description of what this check validates.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    asset_key: AssetKey
    fn: Callable[..., CheckResult | bool]
    description: str | None = None


class CheckRegistry:
    """
    Registry of data quality checks for assets.

    Stores check definitions and provides lookup by asset key.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._checks: dict[AssetKey, list[CheckDefinition]] = {}

    def register(self, check: CheckDefinition) -> None:
        """
        Register a check definition.

        Parameters
        ----------
        check : CheckDefinition
            The check to register.
        """
        if check.asset_key not in self._checks:
            self._checks[check.asset_key] = []
        self._checks[check.asset_key].append(check)

    def get_checks(self, key: AssetKey) -> list[CheckDefinition]:
        """
        Get all checks for an asset.

        Parameters
        ----------
        key : AssetKey
            The asset to get checks for.

        Returns
        -------
        list of CheckDefinition
            All checks registered for this asset.
        """
        return self._checks.get(key, []).copy()

    def all_checks(self) -> list[CheckDefinition]:
        """
        Get all registered checks.

        Returns
        -------
        list of CheckDefinition
            All checks in the registry.
        """
        result = []
        for checks in self._checks.values():
            result.extend(checks)
        return result

    def clear(self) -> None:
        """Clear all registered checks."""
        self._checks.clear()


# Global check registry
_global_check_registry: CheckRegistry | None = None


def get_global_check_registry() -> CheckRegistry:
    """
    Get the global check registry.

    Returns
    -------
    CheckRegistry
        The global check registry singleton.
    """
    global _global_check_registry
    if _global_check_registry is None:
        _global_check_registry = CheckRegistry()
    return _global_check_registry


def run_check(check_def: CheckDefinition, value: Any) -> CheckResult:
    """
    Run a check on a value.

    Parameters
    ----------
    check_def : CheckDefinition
        The check to run.
    value : Any
        The asset value to check.

    Returns
    -------
    CheckResult
        The result of the check.
    """
    started_at = datetime.now()
    try:
        result = check_def.fn(value)

        completed_at = datetime.now()
        duration_ms = (completed_at - started_at).total_seconds() * 1000

        if isinstance(result, CheckResult):
            return result

        # Handle bool return
        passed = bool(result)
        return CheckResult(
            passed=passed,
            check_name=check_def.name,
            asset_key=check_def.asset_key,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            duration_ms=duration_ms,
        )

    except Exception as e:
        completed_at = datetime.now()
        duration_ms = (completed_at - started_at).total_seconds() * 1000
        return CheckResult(
            passed=False,
            check_name=check_def.name,
            asset_key=check_def.asset_key,
            status=CheckStatus.ERROR,
            error=str(e),
            duration_ms=duration_ms,
        )


class AssetWithChecks:
    """
    Wrapper enabling .check decorator on assets.

    This class wraps an AssetDefinition to provide a fluent API for
    attaching data quality checks. It delegates all other attribute
    access to the underlying AssetDefinition.

    Parameters
    ----------
    asset_def : AssetDefinition
        The underlying asset definition.
    registry : CheckRegistry or None
        The check registry to register checks with.
        Defaults to the global check registry.
    """

    def __init__(
        self,
        asset_def: AssetDefinition,
        registry: CheckRegistry | None = None,
    ) -> None:
        """Initialize with asset definition and optional registry."""
        self._asset_def = asset_def
        self._registry = registry if registry is not None else get_global_check_registry()

    def check(
        self,
        fn: Callable[..., CheckResult | bool] | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable[..., CheckResult | bool]:
        """
        Decorator to register a check for this asset.

        Can be used with or without arguments::

            @my_asset.check
            def value_positive(data: dict) -> bool:
                return data["value"] > 0

            @my_asset.check(name="custom_name", description="Validates value")
            def custom_check(data: dict) -> bool:
                return data["value"] > 0

        Parameters
        ----------
        fn : Callable or None
            The check function (when used without arguments).
        name : str or None
            Optional custom name for the check. Defaults to function name.
        description : str or None
            Optional description of the check.

        Returns
        -------
        Callable
            The original check function (for decorator chaining).
        """

        def decorator(
            check_fn: Callable[..., CheckResult | bool],
        ) -> Callable[..., CheckResult | bool]:
            check_name = name if name is not None else check_fn.__name__
            check_def = CheckDefinition(
                name=check_name,
                asset_key=self._asset_def.key,
                fn=check_fn,
                description=description or check_fn.__doc__,
            )
            self._registry.register(check_def)
            return check_fn

        if fn is not None:
            return decorator(fn)
        return decorator  # type: ignore[return-value]

    @property
    def key(self) -> AssetKey:
        """Get the asset key."""
        return self._asset_def.key

    @property
    def fn(self) -> Callable[..., Any]:
        """Get the asset function."""
        return self._asset_def.fn

    @property
    def dependencies(self) -> tuple[AssetKey, ...]:
        """Get the asset dependencies."""
        return self._asset_def.dependencies

    @property
    def dependency_params(self) -> tuple[str, ...]:
        """Get the dependency parameter names."""
        return self._asset_def.dependency_params

    @property
    def return_type(self) -> Any:
        """Get the return type annotation."""
        return self._asset_def.return_type

    @property
    def description(self) -> str | None:
        """Get the asset description."""
        return self._asset_def.description

    @property
    def asset_definition(self) -> AssetDefinition:
        """Get the underlying AssetDefinition."""
        return self._asset_def

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the underlying asset function."""
        return self._asset_def(*args, **kwargs)

    def __hash__(self) -> int:
        """Hash based on the underlying asset definition."""
        return hash(self._asset_def)

    def __eq__(self, other: object) -> bool:
        """Check equality with another AssetWithChecks or AssetDefinition."""
        if isinstance(other, AssetWithChecks):
            return self._asset_def == other._asset_def
        if isinstance(other, AssetDefinition):
            return self._asset_def == other
        return NotImplemented
