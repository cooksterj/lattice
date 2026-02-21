"""
Parser for dbt manifest.json files.

This module provides the ManifestParser class which reads a dbt
manifest.json file and extracts model and test information into
structured Pydantic models.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from lattice.dbt.models import DbtModelInfo, DbtTestInfo

logger = logging.getLogger(__name__)


def _extract_materialization(node: dict[str, Any]) -> str:
    """
    Extract materialization strategy from a dbt node config.

    Parameters
    ----------
    node : dict
        A dbt manifest node dictionary.

    Returns
    -------
    str
        The materialization strategy, defaults to "table".
    """
    config = node.get("config", {})
    return config.get("materialized", "table")


def _extract_model_dependencies(node: dict[str, Any]) -> tuple[str, ...]:
    """
    Extract model-only dependencies from a dbt node.

    Filters depends_on.nodes to only include model references,
    excluding sources, seeds, and other resource types.

    Parameters
    ----------
    node : dict
        A dbt manifest node dictionary.

    Returns
    -------
    tuple of str
        Unique IDs of upstream model dependencies.
    """
    depends_on = node.get("depends_on", {})
    all_deps = depends_on.get("nodes", [])
    return tuple(dep for dep in all_deps if dep.startswith("model."))


def _extract_test_type(node: dict[str, Any]) -> str:
    """
    Extract the test type from a dbt test node.

    Parameters
    ----------
    node : dict
        A dbt manifest test node dictionary.

    Returns
    -------
    str
        The test type name (e.g., "not_null", "unique").
    """
    test_metadata = node.get("test_metadata", {})
    return test_metadata.get("name", "generic")


def _extract_test_model_dependency(node: dict[str, Any]) -> str | None:
    """
    Extract the model that a dbt test depends on.

    Parameters
    ----------
    node : dict
        A dbt manifest test node dictionary.

    Returns
    -------
    str or None
        The unique_id of the first model dependency, or None.
    """
    depends_on = node.get("depends_on", {})
    all_deps = depends_on.get("nodes", [])
    for dep in all_deps:
        if dep.startswith("model."):
            return dep
    return None


def _parse_model_node(unique_id: str, node: dict[str, Any]) -> DbtModelInfo:
    """
    Parse a single dbt model node into a DbtModelInfo.

    Parameters
    ----------
    unique_id : str
        The node's unique identifier.
    node : dict
        The raw node dictionary from the manifest.

    Returns
    -------
    DbtModelInfo
        Parsed model information.

    Raises
    ------
    KeyError
        If required fields are missing from the node.
    """
    return DbtModelInfo(
        unique_id=unique_id,
        name=node["name"],
        description=node.get("description"),
        materialization=_extract_materialization(node),
        schema_name=node.get("schema"),
        database=node.get("database"),
        depends_on=_extract_model_dependencies(node),
        tags=tuple(node.get("tags", [])),
    )


def _parse_test_node(unique_id: str, node: dict[str, Any]) -> DbtTestInfo | None:
    """
    Parse a single dbt test node into a DbtTestInfo.

    Parameters
    ----------
    unique_id : str
        The node's unique identifier.
    node : dict
        The raw node dictionary from the manifest.

    Returns
    -------
    DbtTestInfo or None
        Parsed test information, or None if the test has no model dependency.
    """
    model_dep = _extract_test_model_dependency(node)
    if model_dep is None:
        logger.warning("Test %s has no model dependency, skipping", unique_id)
        return None

    return DbtTestInfo(
        unique_id=unique_id,
        name=node["name"],
        test_type=_extract_test_type(node),
        depends_on_model=model_dep,
        description=node.get("description"),
    )


class ManifestParser:
    """
    Parser for dbt manifest.json files.

    Extracts model and test information from the manifest's nodes section.
    """

    @classmethod
    def parse(cls, manifest_path: str | Path) -> tuple[list[DbtModelInfo], list[DbtTestInfo]]:
        """
        Parse a dbt manifest.json file.

        Parameters
        ----------
        manifest_path : str or Path
            Path to the manifest.json file.

        Returns
        -------
        tuple of (list of DbtModelInfo, list of DbtTestInfo)
            Extracted models and tests.

        Raises
        ------
        FileNotFoundError
            If the manifest file does not exist.
        ValueError
            If the manifest JSON is malformed or missing required structure.
        """
        path = Path(manifest_path)
        if not path.exists():
            raise FileNotFoundError(f"dbt manifest not found: {path}")

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in manifest file: {e}") from e

        if not isinstance(raw, dict):
            raise ValueError("Manifest must be a JSON object")

        nodes = raw.get("nodes", {})
        if not isinstance(nodes, dict):
            raise ValueError("Manifest 'nodes' must be a JSON object")

        models: list[DbtModelInfo] = []
        tests: list[DbtTestInfo] = []

        for unique_id, node in nodes.items():
            if not isinstance(node, dict):
                logger.warning("Skipping non-dict node: %s", unique_id)
                continue

            resource_type = node.get("resource_type", "")

            if resource_type == "model":
                try:
                    model = _parse_model_node(unique_id, node)
                    models.append(model)
                    logger.debug("Parsed dbt model: %s", model.name)
                except (KeyError, ValueError) as e:
                    logger.warning("Failed to parse model %s: %s", unique_id, e)

            elif resource_type == "test":
                try:
                    test = _parse_test_node(unique_id, node)
                    if test is not None:
                        tests.append(test)
                        logger.debug("Parsed dbt test: %s", test.name)
                except (KeyError, ValueError) as e:
                    logger.warning("Failed to parse test %s: %s", unique_id, e)

        logger.info(
            "Parsed %d models and %d tests from %s",
            len(models),
            len(tests),
            path.name,
        )
        return models, tests
