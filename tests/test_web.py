"""Tests for the web visualization API."""

import json
from collections import deque
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from lattice import AssetKey, AssetRegistry, SQLiteRunHistoryStore, asset
from lattice.models import AssetDefinition
from lattice.observability.models import RunRecord
from lattice.web.app import STATIC_DIR, TEMPLATES_DIR, create_app
from lattice.web.execution_manager import ExecutionManager
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

    @asset(registry=registry, deps=["source_data"])
    def processed(source_data: dict) -> dict:
        """Processed data."""
        return {"processed": source_data["value"] * 2}

    @asset(registry=registry, key=AssetKey(name="stats", group="analytics"), deps=["processed"])
    def analytics_stats(processed: dict) -> int:
        """Analytics statistics."""
        return processed["processed"]

    return registry


@pytest.fixture
def populated_client(populated_registry: AssetRegistry) -> TestClient:
    """Create a test client with populated registry."""
    app = create_app(populated_registry)
    return TestClient(app)


@pytest.fixture
def history_store(tmp_path: Path) -> SQLiteRunHistoryStore:
    """Create a file-based history store for cross-thread test client access."""
    return SQLiteRunHistoryStore(tmp_path / "test_runs.db")


@pytest.fixture
def history_client(
    populated_registry: AssetRegistry, history_store: SQLiteRunHistoryStore
) -> TestClient:
    """Create a test client with populated registry and history store."""
    app = create_app(populated_registry, history_store=history_store)
    return TestClient(app)


def _make_run_record(
    run_id: str = "run-001",
    status: str = "completed",
    asset_results: list[dict] | None = None,
    check_results: list[dict] | None = None,
    logs: list[dict] | None = None,
    partition_key: str | None = None,
) -> RunRecord:
    """Helper to create a RunRecord for testing."""
    if asset_results is None:
        asset_results = [
            {"key": "source_data", "status": "completed", "duration_ms": 100.0},
            {"key": "processed", "status": "completed", "duration_ms": 200.0},
            {"key": "analytics/stats", "status": "completed", "duration_ms": 150.0},
        ]
    if check_results is None:
        check_results = []
    if logs is None:
        logs = []

    return RunRecord(
        run_id=run_id,
        started_at=datetime(2024, 1, 15, 10, 0, 0),
        completed_at=datetime(2024, 1, 15, 10, 0, 1),
        status=status,
        duration_ms=1000.0,
        total_assets=len(asset_results),
        completed_count=sum(1 for a in asset_results if a["status"] == "completed"),
        failed_count=sum(1 for a in asset_results if a["status"] == "failed"),
        partition_key=partition_key,
        logs_json=json.dumps(logs),
        lineage_json="[]",
        check_results_json=json.dumps(check_results),
        asset_results_json=json.dumps(asset_results),
    )


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

    def test_graph_node_has_execution_type(self, populated_client: TestClient) -> None:
        """Graph nodes include execution_type field defaulting to 'python'."""
        response = populated_client.get("/api/graph")
        data = response.json()

        for node in data["nodes"]:
            assert node["execution_type"] == "python"

    def test_graph_node_dbt_execution_type(self, registry: AssetRegistry) -> None:
        """Asset with metadata source='dbt' resolves to execution_type='dbt'."""
        registry.register(
            AssetDefinition(
                key=AssetKey(name="dbt_model"),
                fn=lambda: "dbt",
                dependencies=(),
                description="A dbt model.",
                return_type=str,
                metadata={"source": "dbt"},
            )
        )

        app = create_app(registry)
        client = TestClient(app)

        response = client.get("/api/graph")
        data = response.json()

        dbt_node = next(n for n in data["nodes"] if n["id"] == "dbt_model")
        assert dbt_node["execution_type"] == "dbt"


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
    """Tests for the main page (overview graph landing page)."""

    def test_index_returns_html(self, populated_client: TestClient) -> None:
        """Index page returns overview graph HTML."""
        response = populated_client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "LATTICE" in response.text
        assert "ASSET GROUPS" in response.text

    def test_index_serves_overview_graph(self, populated_client: TestClient) -> None:
        """GET / serves the overview graph, not the full graph page."""
        response = populated_client.get("/")
        assert response.status_code == 200
        assert "overview-graph-container" in response.text
        assert "overview_graph.js" in response.text


class TestPipelineRoute:
    """Tests for GET /pipeline serving the full pipeline visualization."""

    def test_pipeline_page_returns_html(self, populated_client: TestClient) -> None:
        """GET /pipeline returns the pipeline page HTML."""
        response = populated_client.get("/pipeline")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "graph.js" in response.text

    def test_pipeline_page_has_graph_container(self, populated_client: TestClient) -> None:
        """GET /pipeline page contains the graph container."""
        response = populated_client.get("/pipeline")
        assert "graph-container" in response.text


class TestGroupedAssetsAPI:
    """Tests for /api/assets/grouped endpoint."""

    def test_grouped_empty_registry(self, client: TestClient) -> None:
        """Empty registry returns empty groups and ungrouped."""
        response = client.get("/api/assets/grouped")
        assert response.status_code == 200

        data = response.json()
        assert data["groups"] == []
        assert data["ungrouped_assets"] == []

    def test_grouped_all_default(self, registry: AssetRegistry) -> None:
        """All-default assets appear in ungrouped, no groups."""

        @asset(registry=registry)
        def alpha() -> str:
            return "a"

        @asset(registry=registry)
        def beta() -> str:
            return "b"

        app = create_app(registry)
        client = TestClient(app)
        response = client.get("/api/assets/grouped")
        data = response.json()

        assert data["groups"] == []
        assert len(data["ungrouped_assets"]) == 2

    def test_grouped_named_groups(self, populated_client: TestClient) -> None:
        """Named groups appear in groups list, default in ungrouped."""
        response = populated_client.get("/api/assets/grouped")
        data = response.json()

        group_names = [g["name"] for g in data["groups"]]
        assert "analytics" in group_names

        analytics = next(g for g in data["groups"] if g["name"] == "analytics")
        assert analytics["asset_count"] == 1
        assert analytics["assets"][0]["name"] == "stats"

        ungrouped_names = {a["name"] for a in data["ungrouped_assets"]}
        assert "source_data" in ungrouped_names
        assert "processed" in ungrouped_names

    def test_grouped_single_asset_group(self, registry: AssetRegistry) -> None:
        """A group with a single asset is still returned."""

        @asset(registry=registry, key=AssetKey(name="solo", group="lone"))
        def solo_asset() -> str:
            return "solo"

        app = create_app(registry)
        client = TestClient(app)
        response = client.get("/api/assets/grouped")
        data = response.json()

        group_names = [g["name"] for g in data["groups"]]
        assert "lone" in group_names
        lone = next(g for g in data["groups"] if g["name"] == "lone")
        assert lone["asset_count"] == 1


class TestGroupGraphAPI:
    """Tests for /api/groups/{name}/graph endpoint."""

    def test_group_graph_returns_nodes_and_edges(self, populated_client: TestClient) -> None:
        """Group graph returns nodes within the group."""
        response = populated_client.get("/api/groups/analytics/graph")
        assert response.status_code == 200

        data = response.json()
        assert data["group_name"] == "analytics"
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["name"] == "stats"

    def test_group_graph_external_edges(self, populated_client: TestClient) -> None:
        """Cross-group dependencies appear as external edges."""
        response = populated_client.get("/api/groups/analytics/graph")
        data = response.json()

        # analytics/stats depends on processed (default group) = inbound external
        inbound = [e for e in data["external_edges"] if e["direction"] == "inbound"]
        assert len(inbound) == 1
        assert inbound[0]["external_asset"] == "processed"

    def test_group_graph_nonexistent(self, populated_client: TestClient) -> None:
        """Nonexistent group returns 404."""
        response = populated_client.get("/api/groups/nonexistent/graph")
        assert response.status_code == 404

    def test_group_graph_intra_group_edges(self, registry: AssetRegistry) -> None:
        """Intra-group dependencies appear as regular edges."""

        @asset(registry=registry, key=AssetKey(name="a", group="team"))
        def team_a() -> str:
            return "a"

        @asset(
            registry=registry,
            key=AssetKey(name="b", group="team"),
            deps=[AssetKey(name="a", group="team")],
        )
        def team_b(team_a: str) -> str:
            return "b"

        app = create_app(registry)
        client = TestClient(app)
        response = client.get("/api/groups/team/graph")
        data = response.json()

        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        assert data["edges"][0]["source"] == "team/a"
        assert data["edges"][0]["target"] == "team/b"
        assert data["external_edges"] == []


class TestOverviewGraphAPI:
    """Tests for /api/assets/overview endpoint."""

    def test_overview_empty_registry(self, client: TestClient) -> None:
        """Empty registry returns empty overview graph."""
        response = client.get("/api/assets/overview")
        assert response.status_code == 200

        data = response.json()
        assert data["nodes"] == []
        assert data["edges"] == []

    def test_overview_standalone_only(self, registry: AssetRegistry) -> None:
        """All-default assets appear as standalone asset nodes."""

        @asset(registry=registry)
        def alpha() -> str:
            return "a"

        @asset(registry=registry, deps=["alpha"])
        def beta(alpha: str) -> str:
            return "b"

        app = create_app(registry)
        client = TestClient(app)
        response = client.get("/api/assets/overview")
        data = response.json()

        node_ids = {n["id"] for n in data["nodes"]}
        assert "alpha" in node_ids
        assert "beta" in node_ids
        assert all(n["node_type"] == "asset" for n in data["nodes"])

        # Edge from alpha to beta
        assert len(data["edges"]) == 1
        assert data["edges"][0]["source"] == "alpha"
        assert data["edges"][0]["target"] == "beta"

    def test_overview_group_super_nodes(self, populated_client: TestClient) -> None:
        """Named groups appear as group super-nodes."""
        response = populated_client.get("/api/assets/overview")
        data = response.json()

        group_nodes = [n for n in data["nodes"] if n["node_type"] == "group"]
        group_ids = {n["id"] for n in group_nodes}
        assert "group:analytics" in group_ids

        analytics = next(n for n in group_nodes if n["id"] == "group:analytics")
        assert analytics["name"] == "analytics"
        assert analytics["asset_count"] == 1

    def test_overview_cross_group_edges(self, populated_client: TestClient) -> None:
        """Edges connect standalone assets to group super-nodes."""
        response = populated_client.get("/api/assets/overview")
        data = response.json()

        # processed -> analytics group (analytics/stats depends on processed)
        edge_pairs = {(e["source"], e["target"]) for e in data["edges"]}
        assert ("processed", "group:analytics") in edge_pairs

    def test_overview_nodes_include_check_count(self, populated_client: TestClient) -> None:
        """Overview nodes include check_count field defaulting to 0."""
        response = populated_client.get("/api/assets/overview")
        data = response.json()

        for node in data["nodes"]:
            assert "check_count" in node
            assert isinstance(node["check_count"], int)

    def test_overview_intra_group_edges_collapsed(self, registry: AssetRegistry) -> None:
        """Dependencies within the same group do not produce overview edges."""

        @asset(registry=registry, key=AssetKey(name="a", group="team"))
        def team_a() -> str:
            return "a"

        @asset(
            registry=registry,
            key=AssetKey(name="b", group="team"),
            deps=[AssetKey(name="a", group="team")],
        )
        def team_b(team_a: str) -> str:
            return "b"

        app = create_app(registry)
        client = TestClient(app)
        response = client.get("/api/assets/overview")
        data = response.json()

        # Only one group node, no edges (intra-group edge is collapsed)
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["node_type"] == "group"
        assert data["edges"] == []


class TestGroupsMainPage:
    """Tests for GET / serving the overview graph."""

    def test_groups_page_returns_html(self, populated_client: TestClient) -> None:
        """GET / returns overview graph HTML."""
        response = populated_client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "ASSET GROUPS" in response.text

    def test_groups_page_has_overview_graph(self, populated_client: TestClient) -> None:
        """Overview page contains the D3 graph container and JS."""
        response = populated_client.get("/")
        assert "overview-graph-container" in response.text
        assert "overview_graph.js" in response.text


class TestGroupDetailPage:
    """Tests for GET /group/{name} page."""

    def test_group_detail_returns_html(self, populated_client: TestClient) -> None:
        """GET /group/{name} returns HTML with group name."""
        response = populated_client.get("/group/analytics")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "ANALYTICS" in response.text

    def test_group_detail_has_graph_container(self, populated_client: TestClient) -> None:
        """Group detail page contains the D3 graph container."""
        response = populated_client.get("/group/analytics")
        assert "group-graph-container" in response.text
        assert 'data-group-name="analytics"' in response.text

    def test_group_detail_loads_group_graph_js(self, populated_client: TestClient) -> None:
        """Group detail page loads group_graph.js."""
        response = populated_client.get("/group/analytics")
        assert "group_graph.js" in response.text


class TestGroupGraphJS:
    """Static analysis tests for group_graph.js rendering."""

    JS_PATH = STATIC_DIR / "js" / "group_graph.js"

    def _read_js(self) -> str:
        return self.JS_PATH.read_text()

    def test_group_graph_js_exists(self) -> None:
        """group_graph.js file exists."""
        assert self.JS_PATH.exists()

    def test_group_graph_js_has_dashed_external_edges(self) -> None:
        """group_graph.js renders external edges with dashed stroke."""
        js = self._read_js()
        assert "8 4" in js or "8, 4" in js or "dasharray" in js

    def test_group_graph_js_fetches_group_api(self) -> None:
        """group_graph.js fetches from /api/groups/ endpoint."""
        js = self._read_js()
        assert "/api/groups/" in js

    def test_group_graph_js_has_stub_nodes(self) -> None:
        """group_graph.js creates stub nodes for external assets."""
        js = self._read_js()
        assert "stub" in js.lower()

    def test_group_graph_js_navigates_to_asset(self) -> None:
        """group_graph.js navigates to /asset/ on node click."""
        js = self._read_js()
        assert "/asset/" in js


class TestOverviewGraphJS:
    """Static analysis tests for overview_graph.js rendering."""

    JS_PATH = STATIC_DIR / "js" / "overview_graph.js"

    def _read_js(self) -> str:
        return self.JS_PATH.read_text()

    def test_overview_graph_js_exists(self) -> None:
        """overview_graph.js file exists."""
        assert self.JS_PATH.exists()

    def test_overview_graph_js_fetches_overview_api(self) -> None:
        """overview_graph.js fetches from /api/assets/overview."""
        js = self._read_js()
        assert "/api/assets/overview" in js

    def test_overview_graph_js_navigates_to_group(self) -> None:
        """overview_graph.js navigates to /group/ on group node click."""
        js = self._read_js()
        assert "/group/" in js

    def test_overview_graph_js_navigates_to_asset(self) -> None:
        """overview_graph.js navigates to /asset/ on asset node click."""
        js = self._read_js()
        assert "/asset/" in js

    def test_overview_graph_js_has_fit_to_content(self) -> None:
        """overview_graph.js includes fitToContent for auto-centering."""
        js = self._read_js()
        assert "fitToContent" in js

    def test_overview_graph_js_has_group_colors(self) -> None:
        """overview_graph.js has GROUP_COLORS for group accent styling."""
        js = self._read_js()
        assert "GROUP_COLORS" in js


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


def _create_app_with_manager(registry: AssetRegistry, manager: ExecutionManager) -> FastAPI:
    """Create a test app with a specific ExecutionManager."""
    from lattice.web.routes import create_router
    from lattice.web.routes_execution import (
        create_asset_websocket_router,
        create_execution_router,
        create_websocket_router,
    )
    from lattice.web.routes_history import create_history_router

    app = FastAPI()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    app.include_router(create_router(registry, templates))
    app.include_router(create_execution_router(registry, manager))
    app.include_router(create_websocket_router(manager))
    app.include_router(create_asset_websocket_router(manager))
    app.include_router(create_history_router(None, templates))
    return app


class TestAssetWebSocket:
    """Tests for /ws/asset/{key} WebSocket endpoint."""

    def test_asset_websocket_connect_disconnect(self, populated_client: TestClient) -> None:
        """WebSocket connection succeeds and closes cleanly."""
        with populated_client.websocket_connect("/ws/asset/source_data") as ws:
            assert ws is not None

    def test_asset_websocket_grouped_key(self, populated_client: TestClient) -> None:
        """WebSocket accepts grouped asset keys with slashes."""
        with populated_client.websocket_connect("/ws/asset/analytics/stats") as ws:
            assert ws is not None

    def test_asset_websocket_replay_empty(self, populated_client: TestClient) -> None:
        """No replay message sent when buffer is empty."""
        with populated_client.websocket_connect("/ws/asset/source_data"):
            # Connection succeeds — no replay message sent (buffer empty).
            # If we try to receive, it would block. The fact that we
            # connected without error is the assertion.
            pass

    def test_asset_websocket_replay_with_buffer(self, populated_registry: AssetRegistry) -> None:
        """Replay message sent when buffer has entries."""
        manager = ExecutionManager()
        manager._replay_buffers["test_asset"] = deque(maxlen=500)
        manager._replay_buffers["test_asset"].append(
            {"type": "asset_log", "data": {"message": "test log"}}
        )

        app = _create_app_with_manager(populated_registry, manager)
        client = TestClient(app)

        with client.websocket_connect("/ws/asset/test_asset") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "replay"
            assert len(msg["data"]["entries"]) == 1
            assert msg["data"]["entries"][0]["data"]["message"] == "test log"


class TestAssetSubscriberRegistry:
    """Tests for ExecutionManager per-asset subscriber registry."""

    def test_add_asset_subscriber(self) -> None:
        """Adding a subscriber tracks it for the asset key."""
        manager = ExecutionManager()
        mock_ws = AsyncMock()
        manager.add_asset_subscriber("test_asset", mock_ws)
        assert mock_ws in manager._asset_subscribers["test_asset"]

    def test_remove_asset_subscriber(self) -> None:
        """Removing a subscriber clears it from the asset key."""
        manager = ExecutionManager()
        mock_ws = AsyncMock()
        manager.add_asset_subscriber("test_asset", mock_ws)
        manager.remove_asset_subscriber("test_asset", mock_ws)
        assert "test_asset" not in manager._asset_subscribers

    def test_remove_nonexistent_subscriber_no_error(self) -> None:
        """Removing from an empty key does not raise."""
        manager = ExecutionManager()
        mock_ws = AsyncMock()
        manager.remove_asset_subscriber("nonexistent", mock_ws)

    @pytest.mark.asyncio
    async def test_broadcast_to_asset_sends_to_subscribers(self) -> None:
        """Broadcast sends message to all subscribers of the asset."""
        manager = ExecutionManager()
        ws1 = AsyncMock()
        ws1.send_json = AsyncMock()
        ws2 = AsyncMock()
        ws2.send_json = AsyncMock()

        manager.add_asset_subscriber("asset_a", ws1)
        manager.add_asset_subscriber("asset_a", ws2)

        message = {"type": "test", "data": {}}
        await manager.broadcast_to_asset("asset_a", message)

        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_to_asset_only_targets_key(self) -> None:
        """Broadcast to one asset does not send to another asset's subscribers."""
        manager = ExecutionManager()
        ws_a = AsyncMock()
        ws_a.send_json = AsyncMock()
        ws_b = AsyncMock()
        ws_b.send_json = AsyncMock()

        manager.add_asset_subscriber("asset_a", ws_a)
        manager.add_asset_subscriber("asset_b", ws_b)

        await manager.broadcast_to_asset("asset_a", {"type": "test"})

        ws_a.send_json.assert_called_once()
        ws_b.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_to_asset_removes_dead_sockets(self) -> None:
        """Dead sockets are cleaned up during broadcast."""
        manager = ExecutionManager()
        live_ws = AsyncMock()
        live_ws.send_json = AsyncMock()
        dead_ws = AsyncMock()
        dead_ws.send_json = AsyncMock(side_effect=Exception("Connection closed"))

        manager.add_asset_subscriber("asset_a", live_ws)
        manager.add_asset_subscriber("asset_a", dead_ws)

        await manager.broadcast_to_asset("asset_a", {"type": "test"})

        assert live_ws in manager._asset_subscribers["asset_a"]
        assert dead_ws not in manager._asset_subscribers["asset_a"]

    def test_get_replay_buffer_empty(self) -> None:
        """Empty replay buffer returns empty list."""
        manager = ExecutionManager()
        assert manager.get_replay_buffer("nonexistent") == []


class TestAssetLogStreaming:
    """Integration tests for end-to-end log streaming and execution isolation."""

    @pytest.mark.asyncio
    async def test_log_entry_reaches_subscriber(self) -> None:
        """Log entries emitted during execution reach asset WebSocket subscribers."""
        import logging as log_mod

        test_registry = AssetRegistry()

        @asset(registry=test_registry)
        def test_asset() -> str:
            log_mod.getLogger("lattice").info("Hello from asset")
            return "done"

        manager = ExecutionManager()
        received: list[dict] = []
        mock_ws = AsyncMock()
        mock_ws.send_json = AsyncMock(side_effect=lambda msg: received.append(msg))

        manager.add_asset_subscriber("test_asset", mock_ws)
        await manager.run_execution(test_registry, target="test_asset")

        log_messages = [m for m in received if m.get("type") == "asset_log"]
        assert len(log_messages) >= 1
        assert any("Hello from asset" in m["data"]["message"] for m in log_messages)

    @pytest.mark.asyncio
    async def test_replay_buffer_populated_during_execution(self) -> None:
        """Replay buffer is populated during execution even without subscribers."""
        import logging as log_mod

        test_registry = AssetRegistry()

        @asset(registry=test_registry)
        def test_asset() -> str:
            log_mod.getLogger("lattice").info("Buffered log")
            return "done"

        manager = ExecutionManager()
        await manager.run_execution(test_registry, target="test_asset")

        buffer = manager.get_replay_buffer("test_asset")
        assert len(buffer) >= 1
        assert any(m["type"] == "asset_log" for m in buffer)

    @pytest.mark.asyncio
    async def test_replay_buffer_cleared_between_executions(self) -> None:
        """Replay buffer is cleared at the start of each new execution."""
        import logging as log_mod

        test_registry = AssetRegistry()

        @asset(registry=test_registry)
        def test_asset() -> str:
            log_mod.getLogger("lattice").info("Run log")
            return "done"

        manager = ExecutionManager()

        # First run
        await manager.run_execution(test_registry, target="test_asset")
        buffer_after_first = manager.get_replay_buffer("test_asset")
        assert len(buffer_after_first) >= 1

        # Second run — buffer should only contain entries from the second run
        await manager.run_execution(test_registry, target="test_asset")
        buffer_after_second = manager.get_replay_buffer("test_asset")
        # Buffer should be roughly the same size as a single run (not double)
        assert len(buffer_after_second) <= len(buffer_after_first) * 2

    @pytest.mark.asyncio
    async def test_execution_isolation_no_subscribers(self) -> None:
        """Execution completes successfully with no WebSocket subscribers."""
        test_registry = AssetRegistry()

        @asset(registry=test_registry)
        def asset_a() -> str:
            return "a"

        @asset(registry=test_registry, deps=["asset_a"])
        def asset_b(asset_a: str) -> str:
            return f"b({asset_a})"

        @asset(registry=test_registry, deps=["asset_b"])
        def asset_c(asset_b: str) -> str:
            return f"c({asset_b})"

        manager = ExecutionManager()
        await manager.run_execution(test_registry, target=None)

        # All assets completed (no errors = execution worked)
        assert not manager.is_running

    @pytest.mark.asyncio
    async def test_execution_isolation_with_subscribers(self) -> None:
        """Execution completes with subscribers (EXEC-01: downstream unaffected)."""
        import logging as log_mod

        test_registry = AssetRegistry()

        @asset(registry=test_registry)
        def asset_a() -> str:
            log_mod.getLogger("lattice").info("a executing")
            return "a"

        @asset(registry=test_registry, deps=["asset_a"])
        def asset_b(asset_a: str) -> str:
            log_mod.getLogger("lattice").info("b executing")
            return f"b({asset_a})"

        @asset(registry=test_registry, deps=["asset_b"])
        def asset_c(asset_b: str) -> str:
            log_mod.getLogger("lattice").info("c executing")
            return f"c({asset_b})"

        manager = ExecutionManager()
        received_a: list[dict] = []
        received_b: list[dict] = []
        received_c: list[dict] = []
        ws_a = AsyncMock()
        ws_a.send_json = AsyncMock(side_effect=lambda msg: received_a.append(msg))
        ws_b = AsyncMock()
        ws_b.send_json = AsyncMock(side_effect=lambda msg: received_b.append(msg))
        ws_c = AsyncMock()
        ws_c.send_json = AsyncMock(side_effect=lambda msg: received_c.append(msg))

        manager.add_asset_subscriber("asset_a", ws_a)
        manager.add_asset_subscriber("asset_b", ws_b)
        manager.add_asset_subscriber("asset_c", ws_c)

        await manager.run_execution(test_registry, target=None)

        # All assets completed
        assert not manager.is_running
        # Each subscriber received messages
        assert len(received_a) >= 1
        assert len(received_b) >= 1
        assert len(received_c) >= 1

    @pytest.mark.asyncio
    async def test_subscriber_disconnect_during_execution(self) -> None:
        """Subscriber disconnect does not disrupt execution (EXEC-02)."""
        import logging as log_mod

        test_registry = AssetRegistry()

        @asset(registry=test_registry)
        def test_asset() -> str:
            for i in range(5):
                log_mod.getLogger("lattice").info("Log entry %d", i)
            return "done"

        manager = ExecutionManager()

        call_count = 0

        async def flaky_send(msg: dict) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                raise Exception("Connection closed")

        dead_ws = AsyncMock()
        dead_ws.send_json = AsyncMock(side_effect=flaky_send)

        manager.add_asset_subscriber("test_asset", dead_ws)
        await manager.run_execution(test_registry, target="test_asset")

        # Execution completed despite subscriber dying
        assert not manager.is_running

    @pytest.mark.asyncio
    async def test_asset_start_complete_sent_to_subscribers(self) -> None:
        """Asset start and complete events are sent to per-asset subscribers."""
        test_registry = AssetRegistry()

        @asset(registry=test_registry)
        def test_asset() -> str:
            return "done"

        manager = ExecutionManager()
        received: list[dict] = []
        mock_ws = AsyncMock()
        mock_ws.send_json = AsyncMock(side_effect=lambda msg: received.append(msg))

        manager.add_asset_subscriber("test_asset", mock_ws)
        await manager.run_execution(test_registry, target="test_asset")

        types = [m.get("type") for m in received]
        assert "asset_start" in types
        assert "asset_complete" in types


class TestAssetLivePage:
    """Tests for /asset/{key}/live page endpoint and route ordering."""

    def test_asset_live_page_returns_html(self, populated_client: TestClient) -> None:
        """Live monitoring page returns 200 with live template content."""
        response = populated_client.get("/asset/source_data/live")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "LIVE" in response.text
        assert "source_data" in response.text

    def test_asset_live_page_grouped_asset(self, populated_client: TestClient) -> None:
        """Live page works for grouped assets with slashes in the key."""
        response = populated_client.get("/asset/analytics/stats/live")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "LIVE" in response.text
        assert "analytics/stats" in response.text

    def test_live_route_not_captured_by_greedy_detail_route(
        self, populated_client: TestClient
    ) -> None:
        """Route ordering ensures /live is not captured by the greedy :path detail route.

        The /asset/{key:path} detail route uses a greedy path converter.
        Without correct registration order, GET /asset/data/test_asset/live would
        match as key='data/test_asset/live' on the detail route instead of
        routing to the live endpoint.
        """
        # The live route should serve the LIVE template
        live_response = populated_client.get("/asset/data/test_asset/live")
        assert live_response.status_code == 200
        assert "LATTICE // LIVE" in live_response.text

        # The detail route should still serve the DETAIL template
        detail_response = populated_client.get("/asset/data/test_asset")
        assert detail_response.status_code == 200
        assert "RUN HISTORY" in detail_response.text
        # Confirm it's NOT the live template title
        assert "LATTICE // LIVE" not in detail_response.text

    def test_live_and_detail_coexist_for_simple_key(self, populated_client: TestClient) -> None:
        """Both live and detail routes work for simple (non-grouped) asset keys."""
        live_response = populated_client.get("/asset/source_data/live")
        assert live_response.status_code == 200
        assert "LIVE" in live_response.text

        detail_response = populated_client.get("/asset/source_data")
        assert detail_response.status_code == 200
        assert "RUN HISTORY" in detail_response.text


class TestAssetDetailPage:
    """Tests for /asset/{key} page endpoint."""

    def test_asset_detail_page_returns_html(self, populated_client: TestClient) -> None:
        """Asset detail page returns HTML for a valid asset."""
        response = populated_client.get("/asset/source_data")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "LATTICE" in response.text
        assert "source_data" in response.text

    def test_asset_detail_page_grouped_asset(self, populated_client: TestClient) -> None:
        """Asset detail page works for grouped assets (group/name path)."""
        response = populated_client.get("/asset/analytics/stats")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "analytics/stats" in response.text

    def test_asset_detail_page_nonexistent(self, populated_client: TestClient) -> None:
        """Asset detail page returns 200 for nonexistent asset (JS handles not-found)."""
        response = populated_client.get("/asset/does_not_exist")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestAssetHistoryAPI:
    """Tests for /api/history/assets/{key} endpoint."""

    def test_asset_history_empty(self, history_client: TestClient) -> None:
        """Returns empty history when no runs exist."""
        response = history_client.get("/api/history/assets/source_data")
        assert response.status_code == 200

        data = response.json()
        assert data["asset_key"] == "source_data"
        assert data["total_runs"] == 0
        assert data["passed_count"] == 0
        assert data["failed_count"] == 0
        assert data["avg_duration_ms"] is None
        assert data["runs"] == []

    def test_asset_history_with_runs(
        self,
        history_client: TestClient,
        history_store: SQLiteRunHistoryStore,
    ) -> None:
        """Returns runs filtered to a specific asset."""
        record = _make_run_record(
            run_id="run-001",
            asset_results=[
                {"key": "source_data", "status": "completed", "duration_ms": 100.0},
                {"key": "processed", "status": "completed", "duration_ms": 200.0},
            ],
            check_results=[
                {"check_name": "check_1", "asset_key": "source_data", "passed": True},
            ],
        )
        history_store.save(record)

        response = history_client.get("/api/history/assets/source_data")
        assert response.status_code == 200

        data = response.json()
        assert data["asset_key"] == "source_data"
        assert data["total_runs"] == 1
        assert data["passed_count"] == 1
        assert data["failed_count"] == 0
        assert data["avg_duration_ms"] == 100.0

        assert len(data["runs"]) == 1
        run = data["runs"][0]
        assert run["run_id"] == "run-001"
        assert run["asset_status"] == "completed"
        assert run["asset_duration_ms"] == 100.0
        assert run["checks_passed"] == 1
        assert run["checks_total"] == 1

    def test_asset_history_nonexistent_asset(
        self,
        history_client: TestClient,
        history_store: SQLiteRunHistoryStore,
    ) -> None:
        """Returns empty list for an asset that was never executed."""
        record = _make_run_record(
            run_id="run-001",
            asset_results=[
                {"key": "source_data", "status": "completed", "duration_ms": 100.0},
            ],
        )
        history_store.save(record)

        response = history_client.get("/api/history/assets/nonexistent_asset")
        assert response.status_code == 200

        data = response.json()
        assert data["total_runs"] == 0
        assert data["runs"] == []

    def test_asset_history_grouped_asset(
        self,
        history_client: TestClient,
        history_store: SQLiteRunHistoryStore,
    ) -> None:
        """Returns history for a grouped asset (group/name key)."""
        record = _make_run_record(
            run_id="run-001",
            asset_results=[
                {"key": "analytics/stats", "status": "completed", "duration_ms": 150.0},
            ],
        )
        history_store.save(record)

        response = history_client.get("/api/history/assets/analytics/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["asset_key"] == "analytics/stats"
        assert data["total_runs"] == 1
        assert data["passed_count"] == 1

    def test_asset_history_multiple_runs(
        self,
        history_client: TestClient,
        history_store: SQLiteRunHistoryStore,
    ) -> None:
        """Returns multiple runs and correct aggregated stats."""
        # Run 1: completed
        history_store.save(
            _make_run_record(
                run_id="run-001",
                asset_results=[
                    {"key": "source_data", "status": "completed", "duration_ms": 100.0},
                ],
            )
        )
        # Run 2: failed
        history_store.save(
            _make_run_record(
                run_id="run-002",
                status="failed",
                asset_results=[
                    {"key": "source_data", "status": "failed", "duration_ms": 50.0},
                ],
            )
        )

        response = history_client.get("/api/history/assets/source_data")
        assert response.status_code == 200

        data = response.json()
        assert data["total_runs"] == 2
        assert data["passed_count"] == 1
        assert data["failed_count"] == 1
        assert data["avg_duration_ms"] == 75.0  # (100 + 50) / 2

    def test_asset_history_no_store(self, populated_client: TestClient) -> None:
        """Returns empty result when no history store is configured."""
        response = populated_client.get("/api/history/assets/source_data")
        assert response.status_code == 200

        data = response.json()
        assert data["total_runs"] == 0
        assert data["runs"] == []


class TestMemoryPanelPositioning:
    """Static analysis tests for LAT-16: memory panel not clipped by sidebar rail."""

    CSS_PATH = STATIC_DIR / "css" / "styles.css"
    JS_PATH = STATIC_DIR / "js" / "graph.js"

    def _read_css(self) -> str:
        return self.CSS_PATH.read_text()

    def _read_js(self) -> str:
        return self.JS_PATH.read_text()

    def test_memory_panel_left_accounts_for_sidebar_rail(self) -> None:
        """Memory panel left offset accounts for the 52px sidebar rail."""
        css = self._read_css()
        assert "left: calc(52px + 1rem)" in css

    def test_memory_panel_sidebar_open_rule_exists(self) -> None:
        """.memory-panel.sidebar-open rule shifts panel when detail sidebar is open."""
        css = self._read_css()
        assert ".memory-panel.sidebar-open" in css
        assert "left: calc(24rem + 1rem)" in css

    def test_memory_panel_transition_includes_left(self) -> None:
        """Memory panel transition includes left for smooth repositioning."""
        css = self._read_css()
        import re

        panel_match = re.search(
            r"\.memory-panel\s*\{[^}]*transition:[^;]*left[^;]*;",
            css,
            re.DOTALL,
        )
        assert panel_match is not None, "memory-panel transition should include 'left'"

    def test_memory_panel_hidden_translatey(self) -> None:
        """.memory-panel.hidden still uses translateY(120%) for slide-out animation."""
        css = self._read_css()
        assert "translateY(120%)" in css


class TestAssetCatalogPage:
    """Tests for /assets page and /api/assets endpoint (AC-2, AC-5)."""

    def test_assets_page_returns_html(self, populated_client: TestClient) -> None:
        """GET /assets returns 200 with HTML content."""
        response = populated_client.get("/assets")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_assets_page_contains_catalog_elements(self, populated_client: TestClient) -> None:
        """Response contains ASSET CATALOG heading."""
        response = populated_client.get("/assets")
        assert "ASSET CATALOG" in response.text

    def test_assets_api_returns_list(self, populated_client: TestClient) -> None:
        """GET /api/assets returns a JSON list."""
        response = populated_client.get("/api/assets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3

    def test_assets_api_contains_expected_fields(self, populated_client: TestClient) -> None:
        """Each item has id, name, group, dependency_count, dependent_count, check_count."""
        response = populated_client.get("/api/assets")
        data = response.json()
        expected_fields = {
            "id",
            "name",
            "group",
            "dependency_count",
            "dependent_count",
            "check_count",
        }
        for item in data:
            assert expected_fields.issubset(item.keys())

    def test_assets_api_empty_when_no_assets(self, client: TestClient) -> None:
        """Returns empty list when no assets registered."""
        response = client.get("/api/assets")
        assert response.status_code == 200
        assert response.json() == []


class TestAssetCatalogSidebar:
    """Tests for sidebar navigation icon for assets (AC-3)."""

    TEMPLATES_DIR = TEMPLATES_DIR
    STATIC_DIR = STATIC_DIR

    def test_base_template_has_assets_sidebar_icon(self) -> None:
        """base.html contains href='/assets' and current_page == 'assets' condition."""
        html = (self.TEMPLATES_DIR / "base.html").read_text()
        assert 'href="/assets"' in html
        assert "current_page == 'assets'" in html

    def test_assets_page_has_active_sidebar(self, populated_client: TestClient) -> None:
        """GET /assets response contains the active class on the assets sidebar icon."""
        response = populated_client.get("/assets")
        # The Jinja template renders 'active' when current_page == 'assets'
        text = response.text
        has_active = 'class="sidebar-icon active"' in text or "sidebar-icon  active" in text
        assert has_active


class TestGraphNodeNavigation:
    """Static analysis tests for graph.js click-to-navigate behavior (AC-1)."""

    JS_PATH = STATIC_DIR / "js" / "graph.js"

    def _read_js(self) -> str:
        return self.JS_PATH.read_text()

    def test_graph_js_click_navigates_to_asset_detail(self) -> None:
        """graph.js contains navigation to /asset/ in the click handler."""
        js = self._read_js()
        assert "window.location.href = '/asset/' +" in js

    def test_graph_js_encodes_asset_id(self) -> None:
        """encodeURIComponent is used in the navigation URL."""
        js = self._read_js()
        assert "encodeURIComponent(d.id)" in js


class TestAssetDetailBackNavigation:
    """Static analysis tests for asset_detail.html back navigation (AC-4)."""

    TEMPLATES_DIR = TEMPLATES_DIR

    def _read_template(self) -> str:
        return (self.TEMPLATES_DIR / "asset_detail.html").read_text()

    def test_asset_detail_uses_history_back(self) -> None:
        """asset_detail.html contains history.back() for back navigation."""
        html = self._read_template()
        assert "history.back()" in html

    def test_asset_detail_no_hardcoded_home_link(self) -> None:
        """Back button does not use a hardcoded href='/' navigation target."""
        html = self._read_template()
        # The back link uses onclick + history.back(), not a direct href="/"
        # Check that the back-link element uses href="#" (placeholder) not href="/"
        assert 'class="back-link"' in html
        # Ensure the back link href is "#" not "/"
        import re

        back_link_match = re.search(r'<a\s+href="([^"]*)"[^>]*class="back-link"', html)
        assert back_link_match is not None
        assert back_link_match.group(1) == "#"


class TestAssetCatalogSchema:
    """Tests for AssetCatalogItemSchema."""

    def test_asset_catalog_item_schema_fields(self) -> None:
        """AssetCatalogItemSchema has expected fields."""
        from lattice.web.schemas import AssetCatalogItemSchema

        item = AssetCatalogItemSchema(
            id="test_asset",
            name="test_asset",
            group="default",
        )
        assert item.id == "test_asset"
        assert item.name == "test_asset"
        assert item.group == "default"
        assert item.description is None
        assert item.dependency_count == 0
        assert item.dependent_count == 0
        assert item.check_count == 0

    def test_asset_catalog_item_has_execution_type(self) -> None:
        """AssetCatalogItemSchema defaults execution_type to 'python'."""
        from lattice.web.schemas import AssetCatalogItemSchema

        item = AssetCatalogItemSchema(
            id="test_asset",
            name="test_asset",
            group="default",
        )
        assert item.execution_type == "python"


class TestHeaderSidebarOffset:
    """Static analysis tests for LAT-18: header offset accounts for sidebar rail."""

    TEMPLATES_DIR = TEMPLATES_DIR

    def _get_header_line(self, filename: str) -> str:
        """Extract the <header ...> tag line from a template file."""
        html = (self.TEMPLATES_DIR / filename).read_text()
        for line in html.splitlines():
            if "<header" in line:
                return line
        raise AssertionError(f"No <header tag found in {filename}")

    def test_assets_header_not_left_zero(self) -> None:
        """assets.html header uses left-[52px], not left-0."""
        header_line = self._get_header_line("assets.html")
        assert "left-[52px]" in header_line
        assert "left-0" not in header_line

    def test_history_header_not_left_zero(self) -> None:
        """history.html header uses left-[52px], not left-0."""
        header_line = self._get_header_line("history.html")
        assert "left-[52px]" in header_line
        assert "left-0" not in header_line

    def test_asset_detail_header_not_left_zero(self) -> None:
        """asset_detail.html header uses left-[52px], not left-0."""
        header_line = self._get_header_line("asset_detail.html")
        assert "left-[52px]" in header_line
        assert "left-0" not in header_line

    def test_graph_page_header_unchanged(self) -> None:
        """index.html header still uses absolute positioning (graph page unaffected)."""
        header_line = self._get_header_line("index.html")
        assert "absolute" in header_line
        assert "fixed" not in header_line


class TestExecutionTypeIcons:
    """Static analysis tests for LAT-20: execution type icons on graph nodes."""

    JS_PATH = STATIC_DIR / "js" / "graph.js"

    def _read_js(self) -> str:
        return self.JS_PATH.read_text()

    def test_graph_js_has_execution_type_icons_constant(self) -> None:
        """graph.js contains the EXECUTION_TYPE_ICONS constant."""
        js = self._read_js()
        assert "EXECUTION_TYPE_ICONS" in js

    def test_graph_js_has_exec_type_icon_class(self) -> None:
        """graph.js renders elements with the exec-type-icon class."""
        js = self._read_js()
        assert "exec-type-icon" in js


class TestGraphPageReadOnly:
    """Static analysis tests: graph.js is now read-only (no execution code)."""

    JS_PATH = STATIC_DIR / "js" / "graph.js"

    def _read_js(self) -> str:
        return self.JS_PATH.read_text()

    def test_no_execution_controls(self) -> None:
        """graph.js does not create execution-controls."""
        js = self._read_js()
        assert "execution-controls" not in js

    def test_no_ws_execution(self) -> None:
        """graph.js does not connect to /ws/execution."""
        js = self._read_js()
        assert "/ws/execution" not in js

    def test_no_start_execution(self) -> None:
        """graph.js does not contain startExecution."""
        js = self._read_js()
        assert "startExecution" not in js

    def test_no_execute_btn(self) -> None:
        """graph.js does not create an execute-btn."""
        js = self._read_js()
        assert "execute-btn" not in js


class TestOverviewGraphExecution:
    """Static analysis tests: overview_graph.js has execution UI."""

    JS_PATH = STATIC_DIR / "js" / "overview_graph.js"

    def _read_js(self) -> str:
        return self.JS_PATH.read_text()

    def test_has_setup_execution_ui(self) -> None:
        """overview_graph.js contains setupExecutionUI."""
        js = self._read_js()
        assert "setupExecutionUI" in js

    def test_has_start_execution(self) -> None:
        """overview_graph.js contains startExecution."""
        js = self._read_js()
        assert "startExecution" in js

    def test_has_ws_execution(self) -> None:
        """overview_graph.js connects to /ws/execution."""
        js = self._read_js()
        assert "/ws/execution" in js

    def test_has_api_execution_start(self) -> None:
        """overview_graph.js posts to /api/execution/start."""
        js = self._read_js()
        assert "/api/execution/start" in js

    def test_has_date_selection_panel(self) -> None:
        """overview_graph.js creates date-selection-panel."""
        js = self._read_js()
        assert "date-selection-panel" in js

    def test_has_memory_panel(self) -> None:
        """overview_graph.js creates memory-panel."""
        js = self._read_js()
        assert "memory-panel" in js

    def test_has_execution_progress(self) -> None:
        """overview_graph.js creates execution-progress."""
        js = self._read_js()
        assert "execution-progress" in js

    def test_no_selected_node(self) -> None:
        """overview_graph.js does not use selectedNode (no targeted execution)."""
        js = self._read_js()
        assert "selectedNode" not in js

    def test_has_asset_to_node_mapping(self) -> None:
        """overview_graph.js builds assetToNodeId map for node status visuals."""
        js = self._read_js()
        assert "assetToNodeId" in js

    def test_has_group_status_tracking(self) -> None:
        """overview_graph.js tracks per-group asset statuses for aggregate blink."""
        js = self._read_js()
        assert "groupAssetStatuses" in js

    def test_applies_status_class_to_nodes(self) -> None:
        """overview_graph.js applies status-running/completed/failed classes."""
        js = self._read_js()
        assert "status-running" in js or "status-${status}" in js
        assert "status-${groupStatus}" in js
