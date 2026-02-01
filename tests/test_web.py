"""Tests for the web visualization API."""

from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from lattice import AssetKey, AssetRegistry, asset
from lattice.web.app import create_app
from lattice.web.execution import ExecutionManager
from lattice.web.schemas_execution import ExecutionStartRequest


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
        assert "LATTICE" in response.text


class TestExecutionStartRequest:
    """Tests for ExecutionStartRequest schema."""

    def test_default_values(self) -> None:
        """Request has expected default values."""
        request = ExecutionStartRequest()
        assert request.target is None
        assert request.include_downstream is False
        assert request.execution_date is None
        assert request.execution_date_end is None

    def test_with_single_date(self) -> None:
        """Request accepts single execution date."""
        request = ExecutionStartRequest(execution_date=date(2024, 1, 15))
        assert request.execution_date == date(2024, 1, 15)
        assert request.execution_date_end is None

    def test_with_date_range(self) -> None:
        """Request accepts date range."""
        request = ExecutionStartRequest(
            execution_date=date(2024, 1, 1),
            execution_date_end=date(2024, 1, 31),
        )
        assert request.execution_date == date(2024, 1, 1)
        assert request.execution_date_end == date(2024, 1, 31)

    def test_with_all_fields(self) -> None:
        """Request accepts all fields."""
        request = ExecutionStartRequest(
            target="my_asset",
            include_downstream=True,
            execution_date=date(2024, 6, 15),
            execution_date_end=date(2024, 6, 20),
        )
        assert request.target == "my_asset"
        assert request.include_downstream is True
        assert request.execution_date == date(2024, 6, 15)
        assert request.execution_date_end == date(2024, 6, 20)

    def test_from_json_string_dates(self) -> None:
        """Request parses dates from JSON strings."""
        request = ExecutionStartRequest.model_validate(
            {
                "execution_date": "2024-03-15",
                "execution_date_end": "2024-03-20",
            }
        )
        assert request.execution_date == date(2024, 3, 15)
        assert request.execution_date_end == date(2024, 3, 20)


class TestExecutionManager:
    """Tests for ExecutionManager date range functionality."""

    @pytest.mark.asyncio
    async def test_run_execution_no_dates(self, registry: AssetRegistry) -> None:
        """Execution without dates runs once with no partition_key."""
        executed_dates: list[date | None] = []

        @asset(registry=registry)
        def simple(partition_key: date | None = None) -> str:
            executed_dates.append(partition_key)
            return "done"

        manager = ExecutionManager()
        await manager.run_execution(registry, target=None)

        assert len(executed_dates) == 1
        assert executed_dates[0] is None

    @pytest.mark.asyncio
    async def test_run_execution_single_date(self, registry: AssetRegistry) -> None:
        """Execution with single date passes partition_key to assets."""
        executed_dates: list[date] = []

        @asset(registry=registry)
        def date_aware(partition_key: date) -> str:
            executed_dates.append(partition_key)
            return f"processed_{partition_key}"

        manager = ExecutionManager()
        test_date = date(2024, 5, 15)
        await manager.run_execution(registry, target=None, execution_date=test_date)

        assert len(executed_dates) == 1
        assert executed_dates[0] == test_date

    @pytest.mark.asyncio
    async def test_run_execution_date_range(self, registry: AssetRegistry) -> None:
        """Execution with date range runs once per date."""
        executed_dates: list[date] = []

        @asset(registry=registry)
        def date_aware(partition_key: date) -> str:
            executed_dates.append(partition_key)
            return f"processed_{partition_key}"

        manager = ExecutionManager()
        start = date(2024, 1, 1)
        end = date(2024, 1, 3)
        await manager.run_execution(
            registry,
            target=None,
            execution_date=start,
            execution_date_end=end,
        )

        assert len(executed_dates) == 3
        assert executed_dates[0] == date(2024, 1, 1)
        assert executed_dates[1] == date(2024, 1, 2)
        assert executed_dates[2] == date(2024, 1, 3)

    @pytest.mark.asyncio
    async def test_run_execution_broadcasts_partition_messages(
        self, registry: AssetRegistry
    ) -> None:
        """Execution broadcasts partition_start and partition_complete messages."""
        messages: list[dict] = []

        @asset(registry=registry)
        def simple() -> str:
            return "done"

        manager = ExecutionManager()
        # Mock the broadcast method to capture messages
        manager.broadcast = AsyncMock(side_effect=lambda msg: messages.append(msg))

        start = date(2024, 2, 1)
        end = date(2024, 2, 2)
        await manager.run_execution(
            registry,
            target=None,
            execution_date=start,
            execution_date_end=end,
        )

        # Filter for partition messages
        partition_starts = [m for m in messages if m.get("type") == "partition_start"]
        partition_completes = [m for m in messages if m.get("type") == "partition_complete"]

        assert len(partition_starts) == 2
        assert partition_starts[0]["data"]["current_date"] == "2024-02-01"
        assert partition_starts[0]["data"]["current_date_index"] == 1
        assert partition_starts[0]["data"]["total_dates"] == 2
        assert partition_starts[1]["data"]["current_date"] == "2024-02-02"
        assert partition_starts[1]["data"]["current_date_index"] == 2

        assert len(partition_completes) == 2
        assert partition_completes[0]["data"]["date"] == "2024-02-01"
        assert partition_completes[1]["data"]["date"] == "2024-02-02"

    @pytest.mark.asyncio
    async def test_run_execution_end_before_start_single_date(
        self, registry: AssetRegistry
    ) -> None:
        """When end date is before start date, only start date is used."""
        executed_dates: list[date] = []

        @asset(registry=registry)
        def date_aware(partition_key: date) -> str:
            executed_dates.append(partition_key)
            return "done"

        manager = ExecutionManager()
        await manager.run_execution(
            registry,
            target=None,
            execution_date=date(2024, 1, 15),
            execution_date_end=date(2024, 1, 10),  # Before start
        )

        # Should only execute for the start date
        assert len(executed_dates) == 1
        assert executed_dates[0] == date(2024, 1, 15)

    @pytest.mark.asyncio
    async def test_run_execution_same_start_end_single_execution(
        self, registry: AssetRegistry
    ) -> None:
        """When start and end are the same date, executes once."""
        executed_dates: list[date] = []

        @asset(registry=registry)
        def date_aware(partition_key: date) -> str:
            executed_dates.append(partition_key)
            return "done"

        manager = ExecutionManager()
        test_date = date(2024, 3, 20)
        await manager.run_execution(
            registry,
            target=None,
            execution_date=test_date,
            execution_date_end=test_date,
        )

        assert len(executed_dates) == 1
        assert executed_dates[0] == test_date
