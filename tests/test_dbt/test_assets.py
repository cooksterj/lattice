"""Tests for dbt asset registration."""

from __future__ import annotations

from pathlib import Path

import pytest

from lattice import AssetRegistry
from lattice.dbt import DBT_GROUP
from lattice.dbt.assets import (
    _build_asset_key,
    _build_dependency_keys,
    _create_check_fn,
    _create_stub_fn,
    _register_checks,
    dbt_assets,
    load_dbt_manifest,
)
from lattice.dbt.models import DbtModelInfo, DbtTestInfo
from lattice.models import AssetKey
from lattice.observability.checks import CheckRegistry


class TestBuildAssetKey:
    """Tests for _build_asset_key helper."""

    def test_produces_dbt_group(self) -> None:
        """Asset key should always use the dbt group."""
        model = DbtModelInfo(unique_id="model.proj.foo", name="foo")
        key = _build_asset_key(model)
        assert key == AssetKey(name="foo", group=DBT_GROUP)
        assert key.group == "dbt"

    def test_uses_model_name(self) -> None:
        """Asset key name should match model name."""
        model = DbtModelInfo(unique_id="model.proj.bar", name="bar")
        key = _build_asset_key(model)
        assert key.name == "bar"


class TestBuildDependencyKeys:
    """Tests for _build_dependency_keys helper."""

    def test_resolves_known_dependencies(self) -> None:
        """Dependencies present in model_map should be resolved."""
        model_a = DbtModelInfo(unique_id="model.proj.a", name="a")
        model_b = DbtModelInfo(
            unique_id="model.proj.b",
            name="b",
            depends_on=("model.proj.a",),
        )
        model_map = {m.unique_id: m for m in [model_a, model_b]}

        deps = _build_dependency_keys(model_b, model_map)
        assert deps == (AssetKey(name="a", group=DBT_GROUP),)

    def test_ignores_unknown_dependencies(self) -> None:
        """Dependencies not in model_map should be filtered out."""
        model = DbtModelInfo(
            unique_id="model.proj.m",
            name="m",
            depends_on=("model.proj.missing",),
        )
        model_map = {"model.proj.m": model}

        deps = _build_dependency_keys(model, model_map)
        assert deps == ()

    def test_no_dependencies(self) -> None:
        """Model with no dependencies returns empty tuple."""
        model = DbtModelInfo(unique_id="model.proj.m", name="m")
        deps = _build_dependency_keys(model, {"model.proj.m": model})
        assert deps == ()

    def test_multiple_dependencies(self) -> None:
        """Multiple valid dependencies are all resolved."""
        models = [DbtModelInfo(unique_id=f"model.proj.dep{i}", name=f"dep{i}") for i in range(3)]
        target = DbtModelInfo(
            unique_id="model.proj.target",
            name="target",
            depends_on=tuple(m.unique_id for m in models),
        )
        model_map = {m.unique_id: m for m in [*models, target]}

        deps = _build_dependency_keys(target, model_map)
        assert len(deps) == 3


class TestCreateStubFn:
    """Tests for _create_stub_fn helper."""

    def test_returns_callable(self) -> None:
        """Stub should be callable."""
        model = DbtModelInfo(
            unique_id="model.proj.m",
            name="test_model",
            materialization="view",
            schema_name="public",
            database="db",
        )
        fn = _create_stub_fn(model, 0)
        assert callable(fn)

    def test_returns_metadata_dict(self) -> None:
        """Stub should return metadata about the model."""
        model = DbtModelInfo(
            unique_id="model.proj.m",
            name="test_model",
            materialization="view",
            schema_name="staging",
            database="analytics",
        )
        fn = _create_stub_fn(model, 0)
        result = fn()

        assert result == {
            "dbt_model": "test_model",
            "materialization": "view",
            "schema": "staging",
            "database": "analytics",
        }

    def test_stub_name_matches_model(self) -> None:
        """Stub function should have the model's name."""
        model = DbtModelInfo(unique_id="model.proj.m", name="my_model")
        fn = _create_stub_fn(model, 0)
        assert fn.__name__ == "my_model"

    def test_stub_accepts_dependency_args(self) -> None:
        """Stub with dependencies should accept the right number of args."""
        model = DbtModelInfo(unique_id="model.proj.m", name="m")
        fn = _create_stub_fn(model, 3)
        result = fn("a", "b", "c")
        assert result["dbt_model"] == "m"

    def test_stub_with_deps_has_correct_param_count(self) -> None:
        """Stub parameter count should match dep_count."""
        import inspect

        model = DbtModelInfo(unique_id="model.proj.m", name="m")
        fn = _create_stub_fn(model, 2)
        sig = inspect.signature(fn)
        assert len(sig.parameters) == 2


class TestCreateCheckFn:
    """Tests for _create_check_fn helper."""

    def test_returns_callable(self) -> None:
        """Check function should be callable."""
        test = DbtTestInfo(
            unique_id="test.proj.t",
            name="not_null_id",
            test_type="not_null",
            depends_on_model="model.proj.m",
        )
        fn = _create_check_fn(test)
        assert callable(fn)

    def test_always_returns_true(self) -> None:
        """dbt check stubs always return True (declarative tests)."""
        test = DbtTestInfo(
            unique_id="test.proj.t",
            name="not_null_id",
            test_type="not_null",
            depends_on_model="model.proj.m",
        )
        fn = _create_check_fn(test)
        assert fn(None) is True
        assert fn("anything") is True


class TestRegisterChecks:
    """Tests for _register_checks helper."""

    def test_registers_checks_for_known_models(self, check_registry: CheckRegistry) -> None:
        """Checks for known models should be registered."""
        model = DbtModelInfo(unique_id="model.proj.m", name="m")
        test = DbtTestInfo(
            unique_id="test.proj.t",
            name="not_null_m_id",
            test_type="not_null",
            depends_on_model="model.proj.m",
        )
        model_map = {"model.proj.m": model}

        count = _register_checks([test], model_map, check_registry)
        assert count == 1

        key = AssetKey(name="m", group=DBT_GROUP)
        checks = check_registry.get_checks(key)
        assert len(checks) == 1
        assert checks[0].name == "not_null_m_id"

    def test_skips_unknown_model_dependency(self, check_registry: CheckRegistry) -> None:
        """Checks depending on unknown models should be skipped."""
        test = DbtTestInfo(
            unique_id="test.proj.t",
            name="not_null_missing_id",
            test_type="not_null",
            depends_on_model="model.proj.missing",
        )

        count = _register_checks([test], {}, check_registry)
        assert count == 0


class TestLoadDbtManifest:
    """Tests for the main load_dbt_manifest function."""

    def test_loads_minimal_manifest(
        self, minimal_manifest: Path, registry: AssetRegistry, check_registry: CheckRegistry
    ) -> None:
        """Load a minimal manifest and verify asset registration."""
        assets = load_dbt_manifest(
            minimal_manifest, registry=registry, check_registry=check_registry
        )

        assert len(assets) == 2
        assert len(registry) == 2

        key_a = AssetKey(name="model_a", group=DBT_GROUP)
        key_b = AssetKey(name="model_b", group=DBT_GROUP)

        assert key_a in registry
        assert key_b in registry

    def test_preserves_dependencies(
        self, minimal_manifest: Path, registry: AssetRegistry, check_registry: CheckRegistry
    ) -> None:
        """Inter-model dependencies should be preserved as AssetKey references."""
        load_dbt_manifest(minimal_manifest, registry=registry, check_registry=check_registry)
        key_b = AssetKey(name="model_b", group=DBT_GROUP)
        asset_b = registry.get(key_b)

        assert AssetKey(name="model_a", group=DBT_GROUP) in asset_b.dependencies

    def test_registers_checks(
        self, minimal_manifest: Path, registry: AssetRegistry, check_registry: CheckRegistry
    ) -> None:
        """dbt tests should be registered as checks."""
        load_dbt_manifest(minimal_manifest, registry=registry, check_registry=check_registry)

        key_a = AssetKey(name="model_a", group=DBT_GROUP)
        checks = check_registry.get_checks(key_a)
        assert len(checks) == 1
        assert checks[0].name == "not_null_model_a_id"

    def test_asset_metadata(
        self, minimal_manifest: Path, registry: AssetRegistry, check_registry: CheckRegistry
    ) -> None:
        """Assets should carry dbt metadata."""
        load_dbt_manifest(minimal_manifest, registry=registry, check_registry=check_registry)
        key_a = AssetKey(name="model_a", group=DBT_GROUP)
        asset_def = registry.get(key_a)

        assert asset_def.metadata is not None
        assert asset_def.metadata["source"] == "dbt"
        assert asset_def.metadata["materialization"] == "table"
        assert asset_def.metadata["schema"] == "public"
        assert asset_def.metadata["database"] == "testdb"
        assert asset_def.metadata["dbt_unique_id"] == "model.test_project.model_a"
        assert asset_def.metadata["tags"] == ["core"]

    def test_asset_return_type_is_dict(
        self, minimal_manifest: Path, registry: AssetRegistry, check_registry: CheckRegistry
    ) -> None:
        """dbt assets should have return_type=dict."""
        load_dbt_manifest(minimal_manifest, registry=registry, check_registry=check_registry)
        key_a = AssetKey(name="model_a", group=DBT_GROUP)
        assert registry.get(key_a).return_type is dict

    def test_asset_description(
        self, minimal_manifest: Path, registry: AssetRegistry, check_registry: CheckRegistry
    ) -> None:
        """Asset description should match model description."""
        load_dbt_manifest(minimal_manifest, registry=registry, check_registry=check_registry)
        key_a = AssetKey(name="model_a", group=DBT_GROUP)
        assert registry.get(key_a).description == "First model"

    def test_empty_manifest_returns_empty(
        self, empty_manifest: Path, registry: AssetRegistry, check_registry: CheckRegistry
    ) -> None:
        """Loading an empty manifest should return no assets."""
        assets = load_dbt_manifest(empty_manifest, registry=registry, check_registry=check_registry)
        assert assets == []
        assert len(registry) == 0

    def test_file_not_found(
        self, tmp_path: Path, registry: AssetRegistry, check_registry: CheckRegistry
    ) -> None:
        """Raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_dbt_manifest(
                tmp_path / "missing.json",
                registry=registry,
                check_registry=check_registry,
            )

    def test_uses_global_registries_by_default(self, minimal_manifest: Path) -> None:
        """When no registries are passed, global ones should be used."""
        from lattice import get_global_registry

        assets = load_dbt_manifest(minimal_manifest)
        assert len(assets) == 2

        global_reg = get_global_registry()
        assert len(global_reg) == 2

    def test_sample_manifest(
        self,
        sample_manifest_path: Path,
        registry: AssetRegistry,
        check_registry: CheckRegistry,
    ) -> None:
        """Load the full sample jaffle_shop manifest."""
        if not sample_manifest_path.exists():
            pytest.skip("sample_manifest.json not found")

        assets = load_dbt_manifest(
            sample_manifest_path, registry=registry, check_registry=check_registry
        )

        assert len(assets) == 8
        assert len(registry) == 8

        # Verify all assets are in the dbt group
        for asset_def in assets:
            assert asset_def.key.group == DBT_GROUP

        # Verify checks were registered
        customers_key = AssetKey(name="customers", group=DBT_GROUP)
        customer_checks = check_registry.get_checks(customers_key)
        assert len(customer_checks) == 2


class TestDbtAssetsDecorator:
    """Tests for the @dbt_assets decorator."""

    def test_decorator_registers_assets(
        self, minimal_manifest: Path, registry: AssetRegistry, check_registry: CheckRegistry
    ) -> None:
        """Decorator should register all manifest models into the registry."""

        @dbt_assets(manifest=minimal_manifest, registry=registry, check_registry=check_registry)
        def my_project(assets):
            pass

        assert len(registry) == 2
        assert AssetKey(name="model_a", group=DBT_GROUP) in registry
        assert AssetKey(name="model_b", group=DBT_GROUP) in registry

    def test_decorator_calls_function_body(
        self, minimal_manifest: Path, registry: AssetRegistry, check_registry: CheckRegistry
    ) -> None:
        """The decorated function body should execute with the asset list."""
        received: list = []

        @dbt_assets(manifest=minimal_manifest, registry=registry, check_registry=check_registry)
        def my_project(assets):
            received.extend(assets)

        assert len(received) == 2

    def test_decorator_returns_original_function(
        self, minimal_manifest: Path, registry: AssetRegistry, check_registry: CheckRegistry
    ) -> None:
        """Decorator should return the original function unchanged."""

        @dbt_assets(manifest=minimal_manifest, registry=registry, check_registry=check_registry)
        def my_project(assets):
            """My project docstring."""

        assert my_project.__name__ == "my_project"
        assert my_project.__doc__ == "My project docstring."

    def test_decorator_registers_checks(
        self, minimal_manifest: Path, registry: AssetRegistry, check_registry: CheckRegistry
    ) -> None:
        """Decorator should register dbt tests as checks."""

        @dbt_assets(manifest=minimal_manifest, registry=registry, check_registry=check_registry)
        def my_project(assets):
            pass

        key_a = AssetKey(name="model_a", group=DBT_GROUP)
        checks = check_registry.get_checks(key_a)
        assert len(checks) == 1
