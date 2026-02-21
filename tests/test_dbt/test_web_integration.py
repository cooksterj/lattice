"""Tests for dbt integration with web API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lattice import AssetRegistry, get_global_check_registry
from lattice.dbt.assets import load_dbt_manifest
from lattice.web.app import create_app


@pytest.fixture
def dbt_registry(minimal_manifest: Path, registry: AssetRegistry) -> AssetRegistry:
    """Load dbt assets into an isolated registry with global check registry."""
    # Routes use get_global_check_registry(), so register checks there
    # (autouse fixture clears it before each test)
    load_dbt_manifest(
        minimal_manifest,
        registry=registry,
        check_registry=get_global_check_registry(),
    )
    return registry


@pytest.fixture
def dbt_client(dbt_registry: AssetRegistry) -> TestClient:
    """Create a test client with dbt assets loaded."""
    app = create_app(dbt_registry)
    return TestClient(app)


class TestGraphEndpoint:
    """Tests for /api/graph with dbt assets."""

    def test_graph_includes_dbt_nodes(self, dbt_client: TestClient) -> None:
        """Graph should include dbt asset nodes."""
        resp = dbt_client.get("/api/graph")
        assert resp.status_code == 200

        data = resp.json()
        node_ids = {n["id"] for n in data["nodes"]}
        assert "dbt/model_a" in node_ids
        assert "dbt/model_b" in node_ids

    def test_graph_dbt_group(self, dbt_client: TestClient) -> None:
        """dbt nodes should have group='dbt'."""
        resp = dbt_client.get("/api/graph")
        data = resp.json()

        for node in data["nodes"]:
            assert node["group"] == "dbt"

    def test_graph_dbt_edges(self, dbt_client: TestClient) -> None:
        """Graph should include dependency edges between dbt models."""
        resp = dbt_client.get("/api/graph")
        data = resp.json()

        edges = [(e["source"], e["target"]) for e in data["edges"]]
        assert ("dbt/model_a", "dbt/model_b") in edges

    def test_graph_metadata_present(self, dbt_client: TestClient) -> None:
        """dbt nodes should include metadata."""
        resp = dbt_client.get("/api/graph")
        data = resp.json()

        model_a = next(n for n in data["nodes"] if n["name"] == "model_a")
        assert model_a["metadata"] is not None
        assert model_a["metadata"]["source"] == "dbt"
        assert model_a["metadata"]["materialization"] == "table"


class TestAssetsEndpoint:
    """Tests for /api/assets with dbt assets."""

    def test_list_includes_dbt_assets(self, dbt_client: TestClient) -> None:
        """Asset catalog should list dbt assets."""
        resp = dbt_client.get("/api/assets")
        assert resp.status_code == 200

        data = resp.json()
        assert len(data) == 2
        names = {a["name"] for a in data}
        assert names == {"model_a", "model_b"}

    def test_list_metadata_present(self, dbt_client: TestClient) -> None:
        """Catalog items should include metadata."""
        resp = dbt_client.get("/api/assets")
        data = resp.json()

        model_a = next(a for a in data if a["name"] == "model_a")
        assert model_a["metadata"] is not None
        assert model_a["metadata"]["source"] == "dbt"

    def test_list_check_count(self, dbt_client: TestClient) -> None:
        """Model A should show 1 check in the catalog."""
        resp = dbt_client.get("/api/assets")
        data = resp.json()

        model_a = next(a for a in data if a["name"] == "model_a")
        assert model_a["check_count"] == 1


class TestAssetDetailEndpoint:
    """Tests for /api/assets/{key} with dbt assets."""

    def test_get_dbt_asset_detail(self, dbt_client: TestClient) -> None:
        """Fetch detailed info for a dbt asset."""
        resp = dbt_client.get("/api/assets/dbt/model_a")
        assert resp.status_code == 200

        data = resp.json()
        assert data["name"] == "model_a"
        assert data["group"] == "dbt"
        assert data["description"] == "First model"
        assert data["return_type"] == "dict"

    def test_detail_includes_metadata(self, dbt_client: TestClient) -> None:
        """Asset detail should include dbt metadata."""
        resp = dbt_client.get("/api/assets/dbt/model_a")
        data = resp.json()

        assert data["metadata"]["source"] == "dbt"
        assert data["metadata"]["materialization"] == "table"
        assert data["metadata"]["schema"] == "public"
        assert data["metadata"]["database"] == "testdb"

    def test_detail_includes_checks(self, dbt_client: TestClient) -> None:
        """Asset detail should list registered checks."""
        resp = dbt_client.get("/api/assets/dbt/model_a")
        data = resp.json()

        assert len(data["checks"]) == 1
        assert data["checks"][0]["name"] == "not_null_model_a_id"

    def test_detail_dependencies(self, dbt_client: TestClient) -> None:
        """Model B detail should show Model A as dependency."""
        resp = dbt_client.get("/api/assets/dbt/model_b")
        data = resp.json()

        assert "dbt/model_a" in data["dependencies"]

    def test_detail_dependents(self, dbt_client: TestClient) -> None:
        """Model A detail should show Model B as dependent."""
        resp = dbt_client.get("/api/assets/dbt/model_a")
        data = resp.json()

        assert "dbt/model_b" in data["dependents"]

    def test_unknown_asset_returns_404(self, dbt_client: TestClient) -> None:
        """Requesting a non-existent asset returns 404."""
        resp = dbt_client.get("/api/assets/dbt/nonexistent")
        assert resp.status_code == 404
