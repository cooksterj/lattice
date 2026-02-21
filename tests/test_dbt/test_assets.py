"""Tests for dbt asset registration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from lattice import AssetRegistry
from lattice.dbt import DBT_GROUP
from lattice.dbt.assets import (
    _build_asset_key,
    _build_dependency_keys,
    _create_stub_fn,
    _filter_models,
    _parse_select,
    _run_dbt_parse,
    dbt_assets,
    load_dbt_manifest,
)
from lattice.dbt.models import DbtModelInfo
from lattice.models import AssetKey


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


class TestLoadDbtManifest:
    """Tests for the main load_dbt_manifest function."""

    def test_loads_minimal_manifest(self, minimal_manifest: Path, registry: AssetRegistry) -> None:
        """Load a minimal manifest and verify asset registration."""
        assets = load_dbt_manifest(minimal_manifest, registry=registry)

        assert len(assets) == 2
        assert len(registry) == 2

        key_a = AssetKey(name="model_a", group=DBT_GROUP)
        key_b = AssetKey(name="model_b", group=DBT_GROUP)

        assert key_a in registry
        assert key_b in registry

    def test_preserves_dependencies(self, minimal_manifest: Path, registry: AssetRegistry) -> None:
        """Inter-model dependencies should be preserved as AssetKey references."""
        load_dbt_manifest(minimal_manifest, registry=registry)
        key_b = AssetKey(name="model_b", group=DBT_GROUP)
        asset_b = registry.get(key_b)

        assert AssetKey(name="model_a", group=DBT_GROUP) in asset_b.dependencies

    def test_asset_metadata(self, minimal_manifest: Path, registry: AssetRegistry) -> None:
        """Assets should carry dbt metadata."""
        load_dbt_manifest(minimal_manifest, registry=registry)
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
        self, minimal_manifest: Path, registry: AssetRegistry
    ) -> None:
        """dbt assets should have return_type=dict."""
        load_dbt_manifest(minimal_manifest, registry=registry)
        key_a = AssetKey(name="model_a", group=DBT_GROUP)
        assert registry.get(key_a).return_type is dict

    def test_asset_description(self, minimal_manifest: Path, registry: AssetRegistry) -> None:
        """Asset description should match model description."""
        load_dbt_manifest(minimal_manifest, registry=registry)
        key_a = AssetKey(name="model_a", group=DBT_GROUP)
        assert registry.get(key_a).description == "First model"

    def test_empty_manifest_returns_empty(
        self, empty_manifest: Path, registry: AssetRegistry
    ) -> None:
        """Loading an empty manifest should return no assets."""
        assets = load_dbt_manifest(empty_manifest, registry=registry)
        assert assets == []
        assert len(registry) == 0

    def test_file_not_found(self, tmp_path: Path, registry: AssetRegistry) -> None:
        """Raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_dbt_manifest(tmp_path / "missing.json", registry=registry)

    def test_uses_global_registries_by_default(self, minimal_manifest: Path) -> None:
        """When no registry is passed, global one should be used."""
        from lattice import get_global_registry

        assets = load_dbt_manifest(minimal_manifest)
        assert len(assets) == 2

        global_reg = get_global_registry()
        assert len(global_reg) == 2

    def test_sample_manifest(
        self,
        sample_manifest_path: Path,
        registry: AssetRegistry,
    ) -> None:
        """Load the full sample jaffle_shop manifest."""
        if not sample_manifest_path.exists():
            pytest.skip("sample_manifest.json not found")

        assets = load_dbt_manifest(sample_manifest_path, registry=registry)

        assert len(assets) == 8
        assert len(registry) == 8

        # Verify all assets are in the dbt group
        for asset_def in assets:
            assert asset_def.key.group == DBT_GROUP


class TestDbtAssetsDecorator:
    """Tests for the @dbt_assets decorator."""

    def test_decorator_registers_assets(
        self, minimal_manifest: Path, registry: AssetRegistry
    ) -> None:
        """Decorator should register all manifest models into the registry."""

        @dbt_assets(manifest=minimal_manifest, registry=registry)
        def my_project(assets):
            pass

        assert len(registry) == 2
        assert AssetKey(name="model_a", group=DBT_GROUP) in registry
        assert AssetKey(name="model_b", group=DBT_GROUP) in registry

    def test_decorator_calls_function_body(
        self, minimal_manifest: Path, registry: AssetRegistry
    ) -> None:
        """The decorated function body should execute with the asset list."""
        received: list = []

        @dbt_assets(manifest=minimal_manifest, registry=registry)
        def my_project(assets):
            received.extend(assets)

        assert len(received) == 2

    def test_decorator_returns_original_function(
        self, minimal_manifest: Path, registry: AssetRegistry
    ) -> None:
        """Decorator should return the original function unchanged."""

        @dbt_assets(manifest=minimal_manifest, registry=registry)
        def my_project(assets):
            """My project docstring."""

        assert my_project.__name__ == "my_project"
        assert my_project.__doc__ == "My project docstring."

    def test_decorator_with_project_dir(
        self, minimal_manifest: Path, registry: AssetRegistry
    ) -> None:
        """Decorator should work with project_dir kwarg."""
        project_dir = minimal_manifest.parent

        def fake_run(*_args, **kwargs):
            from types import SimpleNamespace

            return SimpleNamespace(returncode=0, stderr="")

        with patch("lattice.dbt.assets.subprocess.run", side_effect=fake_run):
            # Place manifest where _run_dbt_parse expects it
            target_dir = project_dir / "target"
            target_dir.mkdir(exist_ok=True)
            import shutil

            shutil.copy(minimal_manifest, target_dir / "manifest.json")

            @dbt_assets(project_dir=project_dir, registry=registry)
            def my_project(assets):
                pass

        assert len(registry) == 2


class TestRunDbtParse:
    """Tests for the _run_dbt_parse helper."""

    def test_missing_directory(self, tmp_path: Path) -> None:
        """Non-existent directory should raise NotADirectoryError."""
        with pytest.raises(NotADirectoryError):
            _run_dbt_parse(tmp_path / "nonexistent")

    def test_not_a_directory(self, tmp_path: Path) -> None:
        """A file path should raise NotADirectoryError."""
        file_path = tmp_path / "somefile.txt"
        file_path.write_text("hello")
        with pytest.raises(NotADirectoryError):
            _run_dbt_parse(file_path)

    def test_parse_failure_raises(self, tmp_path: Path) -> None:
        """Non-zero exit code should raise RuntimeError."""

        def fake_run(*_args, **kwargs):
            from types import SimpleNamespace

            return SimpleNamespace(returncode=1, stderr="Compilation Error")

        with (
            patch("lattice.dbt.assets.subprocess.run", side_effect=fake_run),
            pytest.raises(RuntimeError, match="Compilation Error"),
        ):
            _run_dbt_parse(tmp_path)

    def test_manifest_not_found_after_parse(self, tmp_path: Path) -> None:
        """FileNotFoundError when manifest missing after successful parse."""

        def fake_run(*_args, **kwargs):
            from types import SimpleNamespace

            return SimpleNamespace(returncode=0, stderr="")

        with (
            patch("lattice.dbt.assets.subprocess.run", side_effect=fake_run),
            pytest.raises(FileNotFoundError, match="manifest.json not found"),
        ):
            _run_dbt_parse(tmp_path)

    def test_successful_parse(self, tmp_path: Path) -> None:
        """Successful parse returns manifest path."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        manifest = target_dir / "manifest.json"
        manifest.write_text("{}")

        def fake_run(*_args, **kwargs):
            from types import SimpleNamespace

            assert kwargs["cwd"] == tmp_path
            return SimpleNamespace(returncode=0, stderr="")

        with patch("lattice.dbt.assets.subprocess.run", side_effect=fake_run):
            result = _run_dbt_parse(tmp_path)

        assert result == manifest

    def test_calls_dbt_with_correct_args(self, tmp_path: Path) -> None:
        """Verify dbt is called with --no-partial-parse and correct cwd."""
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        (target_dir / "manifest.json").write_text("{}")

        def fake_run(cmd, **kwargs):
            from types import SimpleNamespace

            assert cmd == ["dbt", "parse", "--no-partial-parse"]
            assert kwargs["cwd"] == tmp_path
            assert kwargs["capture_output"] is True
            assert kwargs["text"] is True
            return SimpleNamespace(returncode=0, stderr="")

        with patch("lattice.dbt.assets.subprocess.run", side_effect=fake_run):
            _run_dbt_parse(tmp_path)


class TestProjectDirIntegration:
    """Tests for project_dir parameter in load_dbt_manifest and dbt_assets."""

    def test_both_params_raises(self, tmp_path: Path, registry: AssetRegistry) -> None:
        """Providing both manifest_path and project_dir raises ValueError."""
        with pytest.raises(ValueError, match="mutually exclusive"):
            load_dbt_manifest(
                tmp_path / "manifest.json",
                project_dir=tmp_path,
                registry=registry,
            )

    def test_neither_param_raises(self, registry: AssetRegistry) -> None:
        """Providing neither manifest_path nor project_dir raises ValueError."""
        with pytest.raises(ValueError, match="must be provided"):
            load_dbt_manifest(registry=registry)

    def test_project_dir_runs_dbt_parse(self, tmp_path: Path, registry: AssetRegistry) -> None:
        """project_dir triggers dbt parse and loads the resulting manifest."""
        # Write a minimal manifest where dbt parse would produce it.
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        manifest_data = {
            "metadata": {"dbt_version": "1.7.0"},
            "nodes": {
                "model.proj.my_model": {
                    "unique_id": "model.proj.my_model",
                    "name": "my_model",
                    "resource_type": "model",
                    "description": "A model",
                    "config": {"materialized": "table"},
                    "depends_on": {"nodes": []},
                    "schema": "public",
                    "database": "db",
                    "tags": [],
                },
            },
        }
        (target_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

        def fake_run(*_args, **kwargs):
            from types import SimpleNamespace

            return SimpleNamespace(returncode=0, stderr="")

        with patch("lattice.dbt.assets.subprocess.run", side_effect=fake_run):
            assets = load_dbt_manifest(project_dir=tmp_path, registry=registry)

        assert len(assets) == 1
        assert assets[0].key.name == "my_model"
        assert len(registry) == 1


class TestParseSelect:
    """Tests for _parse_select helper."""

    def test_valid_tag_selector(self) -> None:
        """'tag:silver' should return ('tag', 'silver')."""
        assert _parse_select("tag:silver") == ("tag", "silver")

    def test_unsupported_selector(self) -> None:
        """Non-tag selectors should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported selector type"):
            _parse_select("config:materialized")

    def test_missing_value(self) -> None:
        """'tag:' with no value should raise ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            _parse_select("tag:")

    def test_no_colon(self) -> None:
        """Bare word without colon should raise ValueError."""
        with pytest.raises(ValueError, match="expected format"):
            _parse_select("silver")


class TestFilterModels:
    """Tests for _filter_models helper."""

    def test_filters_by_tag(self) -> None:
        """Only models with the matching tag should be returned."""
        m1 = DbtModelInfo(unique_id="model.p.a", name="a", tags=("core",))
        m2 = DbtModelInfo(unique_id="model.p.b", name="b", tags=("staging",))
        m3 = DbtModelInfo(unique_id="model.p.c", name="c", tags=("core", "staging"))

        result = _filter_models([m1, m2, m3], "tag:core")
        assert [m.name for m in result] == ["a", "c"]

    def test_no_matches_returns_empty(self) -> None:
        """No matching tag should return an empty list."""
        m1 = DbtModelInfo(unique_id="model.p.a", name="a", tags=("staging",))
        assert _filter_models([m1], "tag:core") == []

    def test_all_match(self) -> None:
        """All models returned when all have the tag."""
        models = [
            DbtModelInfo(unique_id="model.p.a", name="a", tags=("core",)),
            DbtModelInfo(unique_id="model.p.b", name="b", tags=("core",)),
        ]
        result = _filter_models(models, "tag:core")
        assert len(result) == 2


class TestSelectIntegration:
    """Integration tests for select parameter with load_dbt_manifest and dbt_assets."""

    def test_select_filters_manifest(self, minimal_manifest: Path, registry: AssetRegistry) -> None:
        """select='tag:core' should only register model_a (tagged 'core')."""
        assets = load_dbt_manifest(minimal_manifest, select="tag:core", registry=registry)
        assert len(assets) == 1
        assert assets[0].key.name == "model_a"
        assert len(registry) == 1

    def test_select_with_no_matches(self, minimal_manifest: Path, registry: AssetRegistry) -> None:
        """No models match the tag — empty result and empty registry."""
        assets = load_dbt_manifest(minimal_manifest, select="tag:nonexistent", registry=registry)
        assert assets == []
        assert len(registry) == 0

    def test_decorator_with_select(self, minimal_manifest: Path, registry: AssetRegistry) -> None:
        """@dbt_assets with select should only register matching models."""
        received: list = []

        @dbt_assets(manifest=minimal_manifest, select="tag:core", registry=registry)
        def my_project(assets):
            received.extend(assets)

        assert len(received) == 1
        assert received[0].key.name == "model_a"
        assert len(registry) == 1

    def test_cross_tag_dependencies_preserved(
        self, tmp_path: Path, registry: AssetRegistry
    ) -> None:
        """Filtered models should resolve dependencies on models outside the filter.

        Simulates two decorator calls: one for tag:core, another for
        tag:core_final where core_final depends on core.  The second
        call should produce dependency edges pointing to the core models.
        """
        manifest_data = {
            "metadata": {"dbt_version": "1.7.0"},
            "nodes": {
                "model.p.upstream": {
                    "unique_id": "model.p.upstream",
                    "name": "upstream",
                    "resource_type": "model",
                    "description": "Core model",
                    "config": {"materialized": "table"},
                    "depends_on": {"nodes": []},
                    "schema": "public",
                    "database": "db",
                    "tags": ["core"],
                },
                "model.p.downstream": {
                    "unique_id": "model.p.downstream",
                    "name": "downstream",
                    "resource_type": "model",
                    "description": "Final model depending on core",
                    "config": {"materialized": "table"},
                    "depends_on": {"nodes": ["model.p.upstream"]},
                    "schema": "public",
                    "database": "db",
                    "tags": ["core_final"],
                },
            },
        }
        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps(manifest_data), encoding="utf-8")

        # First decorator: register core models
        load_dbt_manifest(manifest, select="tag:core", registry=registry)
        assert len(registry) == 1

        # Second decorator: register core_final models
        assets = load_dbt_manifest(manifest, select="tag:core_final", registry=registry)
        assert len(registry) == 2

        # The downstream asset should have a dependency on upstream
        downstream_def = assets[0]
        assert downstream_def.key.name == "downstream"
        expected_dep = AssetKey(name="upstream", group=DBT_GROUP)
        assert expected_dep in downstream_def.dependencies


class TestDepsParameter:
    """Tests for the deps parameter on dbt_assets and load_dbt_manifest."""

    def test_load_manifest_with_deps(self, minimal_manifest: Path, registry: AssetRegistry) -> None:
        """deps adds upstream dependency edges to every registered model."""
        # Register core first
        core_assets = load_dbt_manifest(minimal_manifest, select="tag:core", registry=registry)
        assert len(core_assets) == 1

        # Register staging with explicit deps on core
        staging_assets = load_dbt_manifest(
            minimal_manifest, select="tag:staging", deps=core_assets, registry=registry
        )
        assert len(staging_assets) == 1

        staging_def = staging_assets[0]
        core_key = AssetKey(name="model_a", group=DBT_GROUP)
        assert core_key in staging_def.dependencies

    def test_deps_deduplicates_with_manifest_deps(
        self, minimal_manifest: Path, registry: AssetRegistry
    ) -> None:
        """When manifest already declares a dep, deps should not duplicate it."""
        # model_b already depends on model_a via manifest depends_on.
        # Passing model_a as an explicit dep should not create a duplicate.
        core_assets = load_dbt_manifest(minimal_manifest, select="tag:core", registry=registry)
        staging_assets = load_dbt_manifest(
            minimal_manifest, select="tag:staging", deps=core_assets, registry=registry
        )

        staging_def = staging_assets[0]
        core_key = AssetKey(name="model_a", group=DBT_GROUP)
        dep_list = list(staging_def.dependencies)
        assert dep_list.count(core_key) == 1

    def test_decorator_deps_links_groups(
        self, minimal_manifest: Path, registry: AssetRegistry
    ) -> None:
        """@dbt_assets deps parameter links groups via decorated functions."""

        @dbt_assets(manifest=minimal_manifest, select="tag:core", registry=registry)
        def core_models(assets):
            pass

        @dbt_assets(
            manifest=minimal_manifest,
            select="tag:staging",
            deps=[core_models],
            registry=registry,
        )
        def final_models(assets):
            pass

        assert len(registry) == 2

        staging_key = AssetKey(name="model_b", group=DBT_GROUP)
        staging_def = registry.get(staging_key)
        core_key = AssetKey(name="model_a", group=DBT_GROUP)
        assert core_key in staging_def.dependencies

    def test_decorator_stores_dbt_assets_attr(
        self, minimal_manifest: Path, registry: AssetRegistry
    ) -> None:
        """Decorated function should have _dbt_assets attribute."""

        @dbt_assets(manifest=minimal_manifest, select="tag:core", registry=registry)
        def core_models(assets):
            pass

        assert hasattr(core_models, "_dbt_assets")
        assert len(core_models._dbt_assets) == 1

    def test_decorator_deps_rejects_non_decorated(
        self, minimal_manifest: Path, registry: AssetRegistry
    ) -> None:
        """Passing a non-@dbt_assets function as deps should raise TypeError."""

        def not_decorated(assets):
            pass

        with pytest.raises(TypeError, match="was not decorated with @dbt_assets"):

            @dbt_assets(
                manifest=minimal_manifest,
                deps=[not_decorated],
                registry=registry,
            )
            def final_models(assets):
                pass

    def test_stub_param_count_includes_deps(
        self, minimal_manifest: Path, registry: AssetRegistry
    ) -> None:
        """Stub function should have params for both manifest and explicit deps."""
        import inspect

        core_assets = load_dbt_manifest(minimal_manifest, select="tag:core", registry=registry)
        staging_assets = load_dbt_manifest(
            minimal_manifest, select="tag:staging", deps=core_assets, registry=registry
        )

        staging_def = staging_assets[0]
        sig = inspect.signature(staging_def.fn)
        assert len(sig.parameters) == len(staging_def.dependencies)
