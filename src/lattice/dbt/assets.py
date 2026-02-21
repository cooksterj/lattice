"""
dbt asset registration for Lattice.

This module provides the ``dbt_assets`` decorator and the lower-level
``load_dbt_manifest`` function.  Both read a dbt manifest.json and
register each model as an individual AssetDefinition in the
AssetRegistry with the "dbt" group.

dbt tests are not mapped to Lattice checks — dbt handles its own
testing via ``dbt test`` and ``.yml`` schema tests.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from lattice.dbt.manifest import ManifestParser
from lattice.dbt.models import DbtModelInfo
from lattice.models import AssetDefinition, AssetKey
from lattice.registry import AssetRegistry, get_global_registry

F = TypeVar("F", bound=Callable[..., Any])

logger = logging.getLogger(__name__)

DBT_GROUP = "dbt"


def _build_asset_key(model: DbtModelInfo) -> AssetKey:
    """
    Build a Lattice AssetKey for a dbt model.

    Parameters
    ----------
    model : DbtModelInfo
        The dbt model metadata.

    Returns
    -------
    AssetKey
        An asset key with group="dbt" and the model's name.
    """
    return AssetKey(name=model.name, group=DBT_GROUP)


def _build_dependency_keys(
    model: DbtModelInfo,
    model_map: dict[str, DbtModelInfo],
) -> tuple[AssetKey, ...]:
    """
    Build dependency AssetKeys for a dbt model.

    Only includes dependencies that are present in the model_map
    (i.e., other dbt models from the same manifest).

    Parameters
    ----------
    model : DbtModelInfo
        The dbt model to resolve dependencies for.
    model_map : dict
        Mapping of unique_id to DbtModelInfo for all parsed models.

    Returns
    -------
    tuple of AssetKey
        Dependency keys for upstream dbt models.
    """
    deps: list[AssetKey] = []
    for dep_id in model.depends_on:
        if dep_id in model_map:
            dep_model = model_map[dep_id]
            deps.append(AssetKey(name=dep_model.name, group=DBT_GROUP))
    return tuple(deps)


def _create_stub_fn(model: DbtModelInfo, dep_count: int) -> Any:
    """
    Create a stub function for a dbt model asset.

    dbt models don't execute Python code, so this stub returns a dict
    with the model's metadata. The function signature includes one
    parameter per dependency so the executor's strict zip passes.

    Parameters
    ----------
    model : DbtModelInfo
        The dbt model to create a stub for.
    dep_count : int
        Number of dependency parameters to accept.

    Returns
    -------
    Callable
        A stub function that accepts dependency args and returns metadata.
    """
    param_names = [f"dep_{i}" for i in range(dep_count)]
    param_list = ", ".join(param_names) if param_names else ""

    metadata = {
        "dbt_model": model.name,
        "materialization": model.materialization,
        "schema": model.schema_name,
        "database": model.database,
    }

    local_ns: dict[str, Any] = {"_metadata": metadata}
    exec(  # noqa: S102
        f"def {model.name}({param_list}):\n    return _metadata",
        local_ns,
    )
    fn = local_ns[model.name]
    fn.__doc__ = model.description or f"dbt model: {model.name}"
    return fn


def load_dbt_manifest(
    manifest_path: str | Path,
    *,
    registry: AssetRegistry | None = None,
) -> list[AssetDefinition]:
    """
    Load a dbt manifest.json and register all models as Lattice assets.

    Each model is registered with ``group="dbt"`` and inter-model
    dependencies are preserved as Lattice dependency edges.

    Parameters
    ----------
    manifest_path : str or Path
        Path to the dbt manifest.json file.
    registry : AssetRegistry or None
        Target asset registry. Defaults to the global registry.

    Returns
    -------
    list of AssetDefinition
        The registered asset definitions.

    Raises
    ------
    FileNotFoundError
        If the manifest file does not exist.
    ValueError
        If the manifest is malformed.
    """
    target_registry = registry if registry is not None else get_global_registry()

    models = ManifestParser.parse(manifest_path)
    model_map = {m.unique_id: m for m in models}

    asset_defs: list[AssetDefinition] = []

    for model in models:
        asset_key = _build_asset_key(model)
        dependencies = _build_dependency_keys(model, model_map)
        stub_fn = _create_stub_fn(model, len(dependencies))

        metadata = {
            "source": "dbt",
            "materialization": model.materialization,
            "schema": model.schema_name,
            "database": model.database,
            "dbt_unique_id": model.unique_id,
            "tags": list(model.tags),
        }

        asset_def = AssetDefinition(
            key=asset_key,
            fn=stub_fn,
            dependencies=dependencies,
            return_type=dict,
            description=model.description,
            metadata=metadata,
        )

        target_registry.register(asset_def)
        asset_defs.append(asset_def)
        logger.info("Registered dbt asset: %s", asset_key)

    logger.info(
        "Loaded %d dbt models from %s",
        len(asset_defs),
        Path(manifest_path).name,
    )

    return asset_defs


def dbt_assets(
    manifest: str | Path,
    *,
    registry: AssetRegistry | None = None,
) -> Callable[[F], F]:
    """
    Decorator that loads a dbt manifest and registers all models as assets.

    The decorated function acts as a declaration point.  Its body is
    executed once at decoration time after all dbt models have been
    registered, receiving the list of created ``AssetDefinition`` objects
    as its sole argument.

    Usage::

        @dbt_assets(manifest="path/to/manifest.json")
        def jaffle_shop(assets):
            '''Jaffle-shop dbt project.'''

    Parameters
    ----------
    manifest : str or Path
        Path to the dbt manifest.json file.
    registry : AssetRegistry or None
        Target asset registry.  Defaults to the global registry.

    Returns
    -------
    Callable
        A decorator that registers dbt assets and returns the original
        function unchanged.
    """

    def decorator(fn: F) -> F:
        assets = load_dbt_manifest(
            manifest,
            registry=registry,
        )
        fn(assets)
        return fn

    return decorator
