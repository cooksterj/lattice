"""
Parser for dbt manifest.json files.

This module provides the ManifestParser class which reads a dbt
manifest.json file and extracts model information into structured
Pydantic models. dbt tests are intentionally not parsed — dbt
handles its own testing via ``dbt test`` and ``.yml`` schema tests.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from lattice.dbt.models import DbtModelInfo

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
    materialization: str = config.get("materialized", "table")
    return materialization


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


class ManifestParser:
    """
    Parser for dbt manifest.json files.

    Extracts model information from the manifest's nodes section.
    dbt tests are not parsed — dbt handles testing via ``dbt test``.
    """

    @classmethod
    def parse(cls, manifest_path: str | Path) -> list[DbtModelInfo]:
        """
        Parse a dbt manifest.json file.

        Parameters
        ----------
        manifest_path : str or Path
            Path to the manifest.json file.

        Returns
        -------
        list of DbtModelInfo
            Extracted models.

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

        logger.info(
            "Parsed %d models from %s",
            len(models),
            path.name,
        )
        return models
