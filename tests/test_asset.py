"""Tests for the @asset decorator and core models."""

import pytest

from lattice import AssetDefinition, AssetKey, AssetRegistry, asset, get_global_registry


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

        assert isinstance(my_asset, AssetDefinition)
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
        assert registry.get("auto_registered") is auto_registered

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

        retrieved = registry.get("my_asset")
        assert retrieved is my_asset

    def test_get_with_asset_key(self, registry: AssetRegistry) -> None:
        @asset(registry=registry)
        def my_asset() -> int:
            return 42

        key = AssetKey(name="my_asset")
        retrieved = registry.get(key)
        assert retrieved is my_asset

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
