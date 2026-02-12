"""Tests for the @asset decorator and core models."""

import pytest

from lattice import (
    AssetKey,
    AssetRegistry,
    AssetWithChecks,
    asset,
    get_global_registry,
)


class TestAssetKey:
    """Tests for AssetKey model."""

    def test_create_with_name_only(self) -> None:
        key = AssetKey(name="my_asset")
        assert key.name == "my_asset"
        assert key.group == "default"

    def test_create_with_group(self) -> None:
        key = AssetKey(name="stats", group="analytics")
        assert key.name == "stats"
        assert key.group == "analytics"

    def test_string_representation_default_group(self) -> None:
        key = AssetKey(name="my_asset")
        assert str(key) == "my_asset"

    def test_string_representation_custom_group(self) -> None:
        key = AssetKey(name="stats", group="analytics")
        assert str(key) == "analytics/stats"

    def test_immutable(self) -> None:
        from pydantic import ValidationError

        key = AssetKey(name="my_asset")
        with pytest.raises(ValidationError):
            key.name = "other"  # type: ignore[misc]

    def test_hashable(self) -> None:
        key1 = AssetKey(name="my_asset")
        key2 = AssetKey(name="my_asset")
        assert hash(key1) == hash(key2)
        assert {key1, key2} == {key1}

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError):
            AssetKey(name="")


class TestAssetDecorator:
    """Tests for the @asset decorator."""

    def test_basic_decoration(self) -> None:
        @asset
        def my_asset() -> int:
            return 42

        # @asset returns AssetWithChecks which wraps AssetDefinition
        assert isinstance(my_asset, AssetWithChecks)
        assert my_asset.key == AssetKey(name="my_asset")
        assert my_asset() == 42

    def test_with_explicit_key(self) -> None:
        @asset(key=AssetKey(name="custom_name", group="custom_group"))
        def my_asset() -> int:
            return 42

        assert my_asset.key.name == "custom_name"
        assert my_asset.key.group == "custom_group"

    def test_dependency_extraction(self) -> None:
        @asset
        def source_a() -> int:
            return 1

        @asset
        def source_b() -> int:
            return 2

        @asset
        def combined(source_a: int, source_b: int) -> int:
            return source_a + source_b

        assert combined.dependencies == (
            AssetKey(name="source_a"),
            AssetKey(name="source_b"),
        )

    def test_explicit_deps_for_grouped_assets(self) -> None:
        """Test that deps parameter allows explicit dependency specification."""

        @asset(
            key=AssetKey(name="dashboard", group="analytics"),
            deps={
                "revenue": AssetKey(name="daily_revenue", group="analytics"),
                "stats": AssetKey(name="user_stats", group="analytics"),
            },
        )
        def dashboard(revenue: dict, stats: dict) -> dict:
            return {"revenue": revenue, "stats": stats}

        assert dashboard.dependencies == (
            AssetKey(name="daily_revenue", group="analytics"),
            AssetKey(name="user_stats", group="analytics"),
        )
        assert dashboard.key == AssetKey(name="dashboard", group="analytics")

    def test_partial_explicit_deps(self) -> None:
        """Test that deps can override some parameters while others use defaults."""

        @asset(
            deps={"grouped_dep": AssetKey(name="source", group="data")},
        )
        def mixed_deps(grouped_dep: int, regular_dep: int) -> int:
            return grouped_dep + regular_dep

        assert mixed_deps.dependencies == (
            AssetKey(name="source", group="data"),
            AssetKey(name="regular_dep"),
        )

    def test_return_type_extraction(self) -> None:
        @asset
        def typed_asset() -> dict[str, int]:
            return {"count": 1}

        assert typed_asset.return_type == dict[str, int]

    def test_description_from_docstring(self) -> None:
        @asset
        def documented_asset() -> int:
            """This is my asset description."""
            return 42

        assert documented_asset.description == "This is my asset description."

    def test_explicit_description(self) -> None:
        @asset(description="Explicit description")
        def my_asset() -> int:
            """Docstring here."""
            return 42

        assert my_asset.description == "Explicit description"

    def test_registers_to_global_registry(self) -> None:
        @asset
        def auto_registered() -> int:
            return 1

        registry = get_global_registry()
        assert "auto_registered" in registry
        # Registry stores AssetDefinition, decorator returns AssetWithChecks
        retrieved = registry.get("auto_registered")
        assert retrieved.key == auto_registered.key

    def test_registers_to_custom_registry(self, registry: AssetRegistry) -> None:
        @asset(registry=registry)
        def custom_registered() -> int:
            return 1

        assert "custom_registered" in registry
        assert "custom_registered" not in get_global_registry()


class TestAssetRegistry:
    """Tests for AssetRegistry."""

    def test_register_and_get(self, registry: AssetRegistry) -> None:
        @asset(registry=registry)
        def my_asset() -> int:
            return 42

        # Registry stores AssetDefinition, decorator returns AssetWithChecks
        retrieved = registry.get("my_asset")
        assert retrieved.key == my_asset.key

    def test_get_with_asset_key(self, registry: AssetRegistry) -> None:
        @asset(registry=registry)
        def my_asset() -> int:
            return 42

        key = AssetKey(name="my_asset")
        retrieved = registry.get(key)
        assert retrieved.key == my_asset.key

    def test_duplicate_registration_raises(self, registry: AssetRegistry) -> None:
        @asset(registry=registry)
        def my_asset() -> int:
            return 1

        with pytest.raises(ValueError, match="already registered"):

            @asset(registry=registry)
            def my_asset() -> int:  # noqa: F811
                return 2

    def test_get_missing_raises(self, registry: AssetRegistry) -> None:
        with pytest.raises(KeyError, match="not found"):
            registry.get("nonexistent")

    def test_iteration(self, registry: AssetRegistry) -> None:
        @asset(registry=registry)
        def asset_a() -> int:
            return 1

        @asset(registry=registry)
        def asset_b() -> int:
            return 2

        assets = list(registry)
        assert len(assets) == 2

    def test_len(self, registry: AssetRegistry) -> None:
        assert len(registry) == 0

        @asset(registry=registry)
        def my_asset() -> int:
            return 1

        assert len(registry) == 1


class TestWrapperMetadata:
    """Tests for _create_async_wrapper and _create_sync_wrapper metadata preservation."""

    def test_sync_wrapper_preserves_name(self) -> None:
        """Sync wrapper preserves __name__."""
        from lattice.asset import _create_sync_wrapper

        def my_function() -> int:
            return 42

        wrapped = _create_sync_wrapper(my_function)
        assert wrapped.__name__ == "my_function"

    def test_sync_wrapper_preserves_doc(self) -> None:
        """Sync wrapper preserves __doc__."""
        from lattice.asset import _create_sync_wrapper

        def my_function() -> int:
            """My docstring."""
            return 42

        wrapped = _create_sync_wrapper(my_function)
        assert wrapped.__doc__ == "My docstring."

    def test_sync_wrapper_delegates_correctly(self) -> None:
        """Sync wrapper calls through to the original function."""
        from lattice.asset import _create_sync_wrapper

        def add(a: int, b: int) -> int:
            return a + b

        wrapped = _create_sync_wrapper(add)
        assert wrapped(3, 4) == 7

    def test_async_wrapper_preserves_name(self) -> None:
        """Async wrapper preserves __name__."""
        from lattice.asset import _create_async_wrapper

        async def my_async_fn() -> int:
            return 42

        wrapped = _create_async_wrapper(my_async_fn)
        assert wrapped.__name__ == "my_async_fn"

    def test_async_wrapper_preserves_doc(self) -> None:
        """Async wrapper preserves __doc__."""
        from lattice.asset import _create_async_wrapper

        async def my_async_fn() -> int:
            """Async docstring."""
            return 42

        wrapped = _create_async_wrapper(my_async_fn)
        assert wrapped.__doc__ == "Async docstring."

    def test_async_wrapper_returns_coroutine_function(self) -> None:
        """Async wrapper is recognized as a coroutine function."""
        import inspect

        from lattice.asset import _create_async_wrapper

        async def my_async_fn() -> int:
            return 42

        wrapped = _create_async_wrapper(my_async_fn)
        assert inspect.iscoroutinefunction(wrapped)


class TestAssetDecoratorFunction:
    """Tests for the _asset_decorator extracted function."""

    def test_produces_correct_asset_with_checks(self, registry: AssetRegistry) -> None:
        """_asset_decorator creates an AssetWithChecks with correct attributes."""
        from lattice.asset import _asset_decorator
        from lattice.observability.checks import AssetWithChecks

        def my_func() -> int:
            """My description."""
            return 42

        result = _asset_decorator(my_func, None, None, None, registry)

        assert isinstance(result, AssetWithChecks)
        assert result.key == AssetKey(name="my_func")
        assert result.description == "My description."
        assert "my_func" in registry

    def test_explicit_key_and_description(self, registry: AssetRegistry) -> None:
        """_asset_decorator respects explicit key and description."""
        from lattice.asset import _asset_decorator

        def my_func() -> int:
            return 42

        key = AssetKey(name="custom", group="grp")
        result = _asset_decorator(my_func, key, None, "Explicit desc", registry)

        assert result.key == key
        assert result.description == "Explicit desc"
