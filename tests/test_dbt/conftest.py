"""Shared fixtures for dbt integration tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lattice.observability.checks import CheckRegistry


@pytest.fixture
def sample_manifest_path() -> Path:
    """Path to the sample dbt manifest."""
    return Path(__file__).parent.parent.parent / "examples" / "sample_manifest.json"


@pytest.fixture
def minimal_manifest(tmp_path: Path) -> Path:
    """Create a minimal valid dbt manifest with two models and one test."""
    manifest: dict[str, Any] = {
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v11/manifest.json",
            "dbt_version": "1.7.0",
            "project_name": "test_project",
        },
        "nodes": {
            "model.test_project.model_a": {
                "unique_id": "model.test_project.model_a",
                "name": "model_a",
                "resource_type": "model",
                "description": "First model",
                "config": {"materialized": "table"},
                "depends_on": {"nodes": []},
                "schema": "public",
                "database": "testdb",
                "tags": ["core"],
            },
            "model.test_project.model_b": {
                "unique_id": "model.test_project.model_b",
                "name": "model_b",
                "resource_type": "model",
                "description": "Second model depending on model_a",
                "config": {"materialized": "view"},
                "depends_on": {"nodes": ["model.test_project.model_a"]},
                "schema": "staging",
                "database": "testdb",
                "tags": ["staging"],
            },
            "test.test_project.not_null_model_a_id": {
                "unique_id": "test.test_project.not_null_model_a_id",
                "name": "not_null_model_a_id",
                "resource_type": "test",
                "description": "ID must not be null",
                "depends_on": {"nodes": ["model.test_project.model_a"]},
                "test_metadata": {"name": "not_null"},
                "tags": [],
            },
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


@pytest.fixture
def empty_manifest(tmp_path: Path) -> Path:
    """Create a manifest with no nodes."""
    manifest: dict[str, Any] = {
        "metadata": {"dbt_version": "1.7.0"},
        "nodes": {},
    }
    path = tmp_path / "empty_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


@pytest.fixture
def check_registry() -> CheckRegistry:
    """Provide a fresh isolated check registry."""
    return CheckRegistry()
