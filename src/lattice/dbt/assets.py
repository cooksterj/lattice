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
import subprocess
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


def _build_asset_key(model: DbtModelInfo, group: str = DBT_GROUP) -> AssetKey:
    """
    Build a Lattice AssetKey for a dbt model.

    Parameters
    ----------
    model : DbtModelInfo
        The dbt model metadata.
    group : str
        Asset group name.  Defaults to ``"dbt"``.

    Returns
    -------
    AssetKey
        An asset key with the given group and the model's name.
    """
    return AssetKey(name=model.name, group=group)


def _build_dependency_keys(
    model: DbtModelInfo,
    model_map: dict[str, DbtModelInfo],
    group: str = DBT_GROUP,
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
    group : str
        Asset group name.  Defaults to ``"dbt"``.

    Returns
    -------
    tuple of AssetKey
        Dependency keys for upstream dbt models.
    """
    deps: list[AssetKey] = []
    for dep_id in model.depends_on:
        if dep_id in model_map:
            dep_model = model_map[dep_id]
            deps.append(AssetKey(name=dep_model.name, group=group))
    return tuple(deps)


def _create_stub_fn(model: DbtModelInfo, dep_count: int) -> Any:
    """
    Create a stub function for a dbt model asset.

    Every ``AssetDefinition`` requires a callable ``fn`` whose parameter
    count exactly matches the number of declared dependencies — the
    executor enforces this with a strict ``zip`` between parameter names
    and upstream results.  Since dbt models are materialised by
    ``dbt build`` (not by Lattice's Python executor), these stubs are
    placeholders that satisfy that contract so dbt models can appear in
    the DAG graph alongside native Lattice assets.

    The function is generated via ``exec()`` rather than a simple
    ``*args`` signature because ``inspect.signature`` on an ``*args``
    function reports parameter names like ``('args', 'kwargs')``, which
    causes the executor's strict zip to fail when the dependency count
    differs.  Generating named parameters (``dep_0``, ``dep_1``, ...)
    ensures an exact match.

    In practice these stubs should never be invoked during a real
    pipeline run; they exist solely to keep the ``AssetDefinition.fn``
    contract intact.

    Parameters
    ----------
    model : DbtModelInfo
        The dbt model to create a stub for.
    dep_count : int
        Number of dependency parameters to accept.  Must match the
        number of resolved upstream dependencies for this model.

    Returns
    -------
    Callable
        A stub function that accepts *dep_count* positional args and
        returns a metadata dict (model name, materialization, schema,
        database).
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


def _run_dbt_parse(project_dir: str | Path) -> Path:
    """Run ``dbt parse`` in the given project directory and return the manifest path.

    Parameters
    ----------
    project_dir : str or Path
        Path to the dbt project root directory.

    Returns
    -------
    Path
        Path to the generated ``target/manifest.json``.

    Raises
    ------
    NotADirectoryError
        If *project_dir* does not exist or is not a directory.
    RuntimeError
        If ``dbt parse`` exits with a non-zero return code.
    FileNotFoundError
        If the manifest file is not found after a successful parse.
    """
    project_dir = Path(project_dir)
    if not project_dir.is_dir():
        raise NotADirectoryError(f"project_dir is not a directory: {project_dir}")

    result = subprocess.run(  # noqa: S603, S607
        ["dbt", "parse", "--no-partial-parse"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"dbt parse failed (exit {result.returncode}):\n{result.stderr}")

    manifest_path = project_dir / "target" / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest.json not found after dbt parse: {manifest_path}")
    return manifest_path


def _parse_select(select: str) -> tuple[str, str]:
    """Parse a select expression like ``tag:silver`` into (selector_type, value).

    Parameters
    ----------
    select : str
        A dbt-style select expression.  Currently only ``tag:<value>`` is
        supported.

    Returns
    -------
    tuple of (str, str)
        The selector type and value, e.g. ``("tag", "silver")``.

    Raises
    ------
    ValueError
        If the expression is not in the form ``tag:<value>``.
    """
    if ":" not in select:
        raise ValueError(f"Invalid select expression {select!r} — expected format 'tag:<value>'")
    selector_type, _, value = select.partition(":")
    if selector_type != "tag":
        raise ValueError(f"Unsupported selector type {selector_type!r} — only 'tag' is supported")
    if not value:
        raise ValueError("Tag value must not be empty in select expression")
    return (selector_type, value)


def _filter_models(
    models: list[DbtModelInfo],
    select: str,
) -> list[DbtModelInfo]:
    """Filter parsed models using a dbt-style select expression.

    Parameters
    ----------
    models : list of DbtModelInfo
        The full list of parsed dbt models.
    select : str
        A dbt-style select expression (e.g. ``tag:silver``).

    Returns
    -------
    list of DbtModelInfo
        Only models matching the select expression.
    """
    selector_type, value = _parse_select(select)
    if selector_type == "tag":
        return [m for m in models if value in m.tags]
    return models  # pragma: no cover


def load_dbt_manifest(
    manifest_path: str | Path | None = None,
    *,
    project_dir: str | Path | None = None,
    select: str | None = None,
    deps: list[AssetDefinition] | None = None,
    registry: AssetRegistry | None = None,
    group: str = DBT_GROUP,
) -> list[AssetDefinition]:
    """
    Load a dbt manifest.json and register all models as Lattice assets.

    Each model is registered with the given *group* and inter-model
    dependencies are preserved as Lattice dependency edges.

    Exactly one of *manifest_path* or *project_dir* must be provided.
    When *project_dir* is given, ``dbt parse --no-partial-parse`` is
    executed automatically and the resulting manifest is loaded.

    Parameters
    ----------
    manifest_path : str, Path, or None
        Path to the dbt manifest.json file.
    project_dir : str, Path, or None
        Path to a dbt project directory.  If provided, ``dbt parse``
        is run first and the manifest is read from
        ``<project_dir>/target/manifest.json``.
    select : str or None
        Optional dbt-style select expression to filter models.
        Currently supports ``tag:<value>`` (e.g. ``"tag:silver"``).
    deps : list of AssetDefinition or None
        Upstream asset definitions that every model in this load should
        depend on.  Use this to create explicit group-level dependency
        edges between separately filtered sets of models.
    registry : AssetRegistry or None
        Target asset registry. Defaults to the global registry.
    group : str
        Asset group name for all registered models.  Defaults to
        ``"dbt"``.

    Returns
    -------
    list of AssetDefinition
        The registered asset definitions.

    Raises
    ------
    ValueError
        If both or neither of *manifest_path* and *project_dir* are given.
    FileNotFoundError
        If the manifest file does not exist.
    ValueError
        If the manifest is malformed or *select* is invalid.
    """
    if manifest_path is not None and project_dir is not None:
        raise ValueError(
            "manifest_path and project_dir are mutually exclusive — "
            "provide one or the other, not both."
        )
    if manifest_path is None and project_dir is None:
        raise ValueError("Either manifest_path or project_dir must be provided.")

    if project_dir is not None:
        manifest_path = _run_dbt_parse(project_dir)

    assert manifest_path is not None  # guaranteed by validation above

    target_registry = registry if registry is not None else get_global_registry()

    all_models = ManifestParser.parse(manifest_path)
    model_map = {m.unique_id: m for m in all_models}

    models = _filter_models(all_models, select) if select is not None else all_models
    extra_dep_keys = tuple(d.key for d in deps) if deps else ()

    asset_defs: list[AssetDefinition] = []

    for model in models:
        asset_key = _build_asset_key(model, group)
        manifest_deps = _build_dependency_keys(model, model_map, group)
        dependencies = tuple(dict.fromkeys(manifest_deps + extra_dep_keys))
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
    manifest: str | Path | None = None,
    *,
    project_dir: str | Path | None = None,
    select: str | None = None,
    deps: list[Callable[..., Any]] | None = None,
    registry: AssetRegistry | None = None,
    group: str = DBT_GROUP,
) -> Callable[[F], F]:
    """
    Decorator that loads a dbt manifest and registers all models as assets.

    The decorated function acts as a declaration point.  Its body is
    executed once at decoration time after all dbt models have been
    registered, receiving the list of created ``AssetDefinition`` objects
    as its sole argument.

    Exactly one of *manifest* or *project_dir* must be provided.

    Usage::

        @dbt_assets(manifest="path/to/manifest.json")
        def jaffle_shop(assets):
            '''Jaffle-shop dbt project.'''

        @dbt_assets(project_dir="/path/to/dbt/project")
        def jaffle_shop(assets):
            '''Runs dbt parse automatically.'''

        @dbt_assets(manifest="path/to/manifest.json", select="tag:core")
        def core_models(assets):
            '''Core layer.'''

        @dbt_assets(manifest="path/to/manifest.json", select="tag:core_final", deps=[core_models])
        def final_models(assets):
            '''Final layer — depends on core.'''

    Parameters
    ----------
    manifest : str, Path, or None
        Path to the dbt manifest.json file.
    project_dir : str, Path, or None
        Path to a dbt project directory.  ``dbt parse`` is run
        automatically before loading the manifest.
    select : str or None
        Optional dbt-style select expression to filter models.
        Currently supports ``tag:<value>`` (e.g. ``"tag:silver"``).
    deps : list of callables or None
        Functions previously decorated with ``@dbt_assets``.  Every
        model registered by *this* decorator will depend on all assets
        from the referenced groups, creating explicit group-level
        dependency edges in the DAG.
    registry : AssetRegistry or None
        Target asset registry.  Defaults to the global registry.
    group : str
        Asset group name for all registered models.  Defaults to
        ``"dbt"``.

    Returns
    -------
    Callable
        A decorator that registers dbt assets and returns the original
        function unchanged.
    """

    def decorator(fn: F) -> F:
        dep_assets: list[AssetDefinition] = []
        if deps:
            for dep_fn in deps:
                fn_assets = getattr(dep_fn, "_dbt_assets", None)
                if fn_assets is None:
                    raise TypeError(f"{dep_fn.__name__!r} was not decorated with @dbt_assets")
                dep_assets.extend(fn_assets)

        assets = load_dbt_manifest(
            manifest,
            project_dir=project_dir,
            select=select,
            deps=dep_assets or None,
            registry=registry,
            group=group,
        )
        fn._dbt_assets = assets  # type: ignore[attr-defined]
        fn(assets)
        return fn

    return decorator
