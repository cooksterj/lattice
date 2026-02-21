"""Tests for dbt manifest parsing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lattice.dbt.manifest import ManifestParser


class TestManifestParser:
    """Tests for ManifestParser.parse class method."""

    def test_parse_minimal_manifest(self, minimal_manifest: Path) -> None:
        """Parse a minimal manifest with two models."""
        models = ManifestParser.parse(minimal_manifest)

        assert len(models) == 2

        model_names = {m.name for m in models}
        assert model_names == {"model_a", "model_b"}

    def test_parse_model_fields(self, minimal_manifest: Path) -> None:
        """Verify parsed model fields are correct."""
        models = ManifestParser.parse(minimal_manifest)
        model_map = {m.name: m for m in models}

        model_a = model_map["model_a"]
        assert model_a.unique_id == "model.test_project.model_a"
        assert model_a.materialization == "table"
        assert model_a.schema_name == "public"
        assert model_a.database == "testdb"
        assert model_a.depends_on == ()
        assert model_a.tags == ("core",)

    def test_parse_model_dependencies(self, minimal_manifest: Path) -> None:
        """Model B should depend on Model A."""
        models = ManifestParser.parse(minimal_manifest)
        model_map = {m.name: m for m in models}

        model_b = model_map["model_b"]
        assert model_b.depends_on == ("model.test_project.model_a",)

    def test_parse_filters_source_dependencies(self, tmp_path: Path) -> None:
        """Source-only dependencies should be filtered from depends_on."""
        manifest: dict[str, Any] = {
            "nodes": {
                "model.proj.m": {
                    "unique_id": "model.proj.m",
                    "name": "m",
                    "resource_type": "model",
                    "config": {"materialized": "table"},
                    "depends_on": {
                        "nodes": [
                            "source.proj.raw.data",
                            "model.proj.upstream",
                        ]
                    },
                    "tags": [],
                },
                "model.proj.upstream": {
                    "unique_id": "model.proj.upstream",
                    "name": "upstream",
                    "resource_type": "model",
                    "config": {},
                    "depends_on": {"nodes": []},
                    "tags": [],
                },
            },
        }
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(manifest))

        models = ManifestParser.parse(path)
        model_map = {m.name: m for m in models}
        assert model_map["m"].depends_on == ("model.proj.upstream",)

    def test_parse_empty_manifest(self, empty_manifest: Path) -> None:
        """An empty manifest returns no models."""
        models = ManifestParser.parse(empty_manifest)
        assert models == []

    def test_parse_sample_manifest(self, sample_manifest_path: Path) -> None:
        """Parse the full sample jaffle_shop manifest."""
        if not sample_manifest_path.exists():
            pytest.skip("sample_manifest.json not found")

        models = ManifestParser.parse(sample_manifest_path)
        assert len(models) == 8

        model_names = {m.name for m in models}
        assert "stg_customers" in model_names
        assert "customers" in model_names
        assert "revenue_daily" in model_names

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Raise FileNotFoundError for missing manifest."""
        with pytest.raises(FileNotFoundError, match="dbt manifest not found"):
            ManifestParser.parse(tmp_path / "nonexistent.json")

    def test_invalid_json(self, tmp_path: Path) -> None:
        """Raise ValueError for invalid JSON."""
        path = tmp_path / "bad.json"
        path.write_text("not json at all")
        with pytest.raises(ValueError, match="Invalid JSON"):
            ManifestParser.parse(path)

    def test_non_object_manifest(self, tmp_path: Path) -> None:
        """Raise ValueError when manifest is not a JSON object."""
        path = tmp_path / "array.json"
        path.write_text("[1, 2, 3]")
        with pytest.raises(ValueError, match="must be a JSON object"):
            ManifestParser.parse(path)

    def test_non_object_nodes(self, tmp_path: Path) -> None:
        """Raise ValueError when nodes is not an object."""
        path = tmp_path / "bad_nodes.json"
        path.write_text(json.dumps({"nodes": [1, 2, 3]}))
        with pytest.raises(ValueError, match="'nodes' must be a JSON object"):
            ManifestParser.parse(path)

    def test_skips_non_dict_node(self, tmp_path: Path) -> None:
        """Gracefully skip nodes that are not dicts."""
        manifest: dict[str, Any] = {
            "nodes": {
                "model.proj.ok": {
                    "unique_id": "model.proj.ok",
                    "name": "ok",
                    "resource_type": "model",
                    "config": {},
                    "depends_on": {"nodes": []},
                    "tags": [],
                },
                "bad_node": "not a dict",
            },
        }
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(manifest))

        models = ManifestParser.parse(path)
        assert len(models) == 1
        assert models[0].name == "ok"

    def test_skips_malformed_model(self, tmp_path: Path) -> None:
        """Gracefully skip models missing required fields."""
        manifest: dict[str, Any] = {
            "nodes": {
                "model.proj.bad": {
                    "unique_id": "model.proj.bad",
                    "resource_type": "model",
                    # Missing "name" field
                },
            },
        }
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(manifest))

        models = ManifestParser.parse(path)
        assert len(models) == 0

    def test_default_materialization(self, tmp_path: Path) -> None:
        """Default materialization should be 'table' when config is empty."""
        manifest: dict[str, Any] = {
            "nodes": {
                "model.proj.m": {
                    "unique_id": "model.proj.m",
                    "name": "m",
                    "resource_type": "model",
                    "config": {},
                    "depends_on": {"nodes": []},
                    "tags": [],
                },
            },
        }
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(manifest))

        models = ManifestParser.parse(path)
        assert models[0].materialization == "table"

    def test_ignores_test_nodes(self, tmp_path: Path) -> None:
        """Test nodes should not be parsed as models."""
        manifest: dict[str, Any] = {
            "nodes": {
                "test.proj.not_null_id": {
                    "unique_id": "test.proj.not_null_id",
                    "name": "not_null_id",
                    "resource_type": "test",
                    "depends_on": {"nodes": ["model.proj.m"]},
                    "test_metadata": {"name": "not_null"},
                    "tags": [],
                },
            },
        }
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(manifest))

        models = ManifestParser.parse(path)
        assert models == []

    def test_ignores_source_nodes(self, tmp_path: Path) -> None:
        """Source nodes should not be parsed as models."""
        manifest: dict[str, Any] = {
            "nodes": {
                "source.proj.raw.data": {
                    "unique_id": "source.proj.raw.data",
                    "name": "data",
                    "resource_type": "source",
                    "schema": "raw",
                    "database": "db",
                },
            },
        }
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(manifest))

        models = ManifestParser.parse(path)
        assert models == []
