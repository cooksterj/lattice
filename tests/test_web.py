"""Tests for the web visualization API."""

import pytest
from fastapi.testclient import TestClient

from lattice import AssetKey, AssetRegistry, asset
from lattice.web.app import create_app


@pytest.fixture
def client(registry: AssetRegistry) -> TestClient:
    """Create a test client with the given registry."""
    app = create_app(registry)
    return TestClient(app)


@pytest.fixture
def populated_registry(registry: AssetRegistry) -> AssetRegistry:
    """Create a registry with sample assets."""

    @asset(registry=registry)
    def source_data() -> dict:
        """Raw source data."""
        return {"value": 1}

    @asset(registry=registry)
    def processed(source_data: dict) -> dict:
        """Processed data."""
        return {"processed": source_data["value"] * 2}

    @asset(registry=registry, key=AssetKey(name="stats", group="analytics"))
    def analytics_stats(processed: dict) -> int:
        """Analytics statistics."""
        return processed["processed"]

    return registry


@pytest.fixture
def populated_client(populated_registry: AssetRegistry) -> TestClient:
    """Create a test client with populated registry."""
    app = create_app(populated_registry)
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_empty_registry(self, client: TestClient) -> None:
        """Health check works with empty registry."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["asset_count"] == 0
        assert "version" in data

    def test_health_with_assets(self, populated_client: TestClient) -> None:
        """Health check reports correct asset count."""
        response = populated_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["asset_count"] == 3


class TestGraphEndpoint:
    """Tests for /api/graph endpoint."""

    def test_graph_empty_registry(self, client: TestClient) -> None:
        """Empty registry returns empty graph."""
        response = client.get("/api/graph")
        assert response.status_code == 200

        data = response.json()
        assert data["nodes"] == []
        assert data["edges"] == []

    def test_graph_nodes(self, populated_client: TestClient) -> None:
        """Graph contains all assets as nodes."""
        response = populated_client.get("/api/graph")
        assert response.status_code == 200

        data = response.json()
        assert len(data["nodes"]) == 3

        node_ids = {n["id"] for n in data["nodes"]}
        assert "source_data" in node_ids
        assert "processed" in node_ids
        assert "analytics/stats" in node_ids

    def test_graph_edges(self, populated_client: TestClient) -> None:
        """Graph contains dependency edges."""
        response = populated_client.get("/api/graph")
        assert response.status_code == 200

        data = response.json()
        edges = data["edges"]

        # processed depends on source_data
        assert {"source": "source_data", "target": "processed"} in edges

        # analytics/stats depends on processed
        assert {"source": "processed", "target": "analytics/stats"} in edges

    def test_graph_node_properties(self, populated_client: TestClient) -> None:
        """Graph nodes have expected properties."""
        response = populated_client.get("/api/graph")
        data = response.json()

        source_node = next(n for n in data["nodes"] if n["id"] == "source_data")
        assert source_node["name"] == "source_data"
        assert source_node["group"] == "default"
        assert source_node["description"] == "Raw source data."
        assert source_node["return_type"] == "dict"
        assert source_node["dependency_count"] == 0
        assert source_node["dependent_count"] == 1


class TestAssetDetailEndpoint:
    """Tests for /api/assets/{key} endpoint."""

    def test_asset_not_found(self, client: TestClient) -> None:
        """Returns 404 for nonexistent asset."""
        response = client.get("/api/assets/nonexistent")
        assert response.status_code == 404

    def test_asset_by_name(self, populated_client: TestClient) -> None:
        """Get asset by simple name."""
        response = populated_client.get("/api/assets/source_data")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "source_data"
        assert data["group"] == "default"
        assert data["dependencies"] == []
        assert data["dependents"] == ["processed"]

    def test_asset_by_group_name(self, populated_client: TestClient) -> None:
        """Get asset by group/name path."""
        response = populated_client.get("/api/assets/analytics/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "stats"
        assert data["group"] == "analytics"
        assert data["dependencies"] == ["processed"]
        assert data["dependents"] == []

    def test_asset_with_dependencies(self, populated_client: TestClient) -> None:
        """Asset shows its dependencies."""
        response = populated_client.get("/api/assets/processed")
        assert response.status_code == 200

        data = response.json()
        assert data["dependencies"] == ["source_data"]
        assert data["dependents"] == ["analytics/stats"]


class TestPlanEndpoint:
    """Tests for /api/plan endpoint."""

    def test_plan_empty_registry(self, client: TestClient) -> None:
        """Empty registry returns empty plan."""
        response = client.get("/api/plan")
        assert response.status_code == 200

        data = response.json()
        assert data["steps"] == []
        assert data["total_assets"] == 0
        assert data["target"] is None

    def test_plan_full(self, populated_client: TestClient) -> None:
        """Full plan includes all assets in order."""
        response = populated_client.get("/api/plan")
        assert response.status_code == 200

        data = response.json()
        assert data["total_assets"] == 3
        assert data["target"] is None

        # Check ordering - source_data should be before processed
        step_ids = [s["id"] for s in data["steps"]]
        assert step_ids.index("source_data") < step_ids.index("processed")
        assert step_ids.index("processed") < step_ids.index("analytics/stats")

    def test_plan_with_target(self, populated_client: TestClient) -> None:
        """Plan with target includes only required assets."""
        response = populated_client.get("/api/plan?target=processed")
        assert response.status_code == 200

        data = response.json()
        assert data["target"] == "processed"
        assert data["total_assets"] == 2

        step_ids = [s["id"] for s in data["steps"]]
        assert "source_data" in step_ids
        assert "processed" in step_ids
        assert "analytics/stats" not in step_ids

    def test_plan_target_not_found(self, populated_client: TestClient) -> None:
        """Plan with nonexistent target returns 404."""
        response = populated_client.get("/api/plan?target=nonexistent")
        assert response.status_code == 404

    def test_plan_step_properties(self, populated_client: TestClient) -> None:
        """Plan steps have expected properties."""
        response = populated_client.get("/api/plan")
        data = response.json()

        first_step = data["steps"][0]
        assert "order" in first_step
        assert "id" in first_step
        assert "name" in first_step
        assert "group" in first_step
        assert first_step["order"] == 1


class TestIndexPage:
    """Tests for the main visualization page."""

    def test_index_returns_html(self, populated_client: TestClient) -> None:
        """Index page returns HTML."""
        response = populated_client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Lattice" in response.text
