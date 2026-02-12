"""Tests for asset checks module."""

from lattice import AssetKey, AssetRegistry, asset
from lattice.models import AssetDefinition
from lattice.observability.checks import (
    AssetWithChecks,
    CheckDefinition,
    CheckRegistry,
    get_global_check_registry,
    run_check,
)
from lattice.observability.models import CheckResult, CheckStatus


class TestCheckDefinition:
    """Tests for CheckDefinition model."""

    def test_check_definition_creation(self):
        def my_check(value: int) -> bool:
            return value > 0

        check_def = CheckDefinition(
            name="positive_check",
            asset_key=AssetKey(name="my_asset"),
            fn=my_check,
            description="Checks value is positive",
        )
        assert check_def.name == "positive_check"
        assert check_def.asset_key.name == "my_asset"
        assert check_def.description == "Checks value is positive"


class TestCheckRegistry:
    """Tests for CheckRegistry."""

    def test_register_and_get_checks(self):
        registry = CheckRegistry()

        def check1(value: int) -> bool:
            return value > 0

        def check2(value: int) -> bool:
            return value < 100

        asset_key = AssetKey(name="my_asset")
        registry.register(CheckDefinition(name="check1", asset_key=asset_key, fn=check1))
        registry.register(CheckDefinition(name="check2", asset_key=asset_key, fn=check2))

        checks = registry.get_checks(asset_key)
        assert len(checks) == 2
        assert checks[0].name == "check1"
        assert checks[1].name == "check2"

    def test_get_checks_empty(self):
        registry = CheckRegistry()
        checks = registry.get_checks(AssetKey(name="nonexistent"))
        assert checks == []

    def test_all_checks(self):
        registry = CheckRegistry()

        def check1(v):
            return True

        def check2(v):
            return True

        registry.register(CheckDefinition(name="check1", asset_key=AssetKey(name="a"), fn=check1))
        registry.register(CheckDefinition(name="check2", asset_key=AssetKey(name="b"), fn=check2))

        all_checks = registry.all_checks()
        assert len(all_checks) == 2

    def test_clear(self):
        registry = CheckRegistry()
        registry.register(
            CheckDefinition(name="check", asset_key=AssetKey(name="a"), fn=lambda v: True)
        )
        registry.clear()
        assert registry.all_checks() == []


class TestRunCheck:
    """Tests for run_check function."""

    def test_run_check_passes_bool(self):
        def my_check(value: int) -> bool:
            return value > 0

        check_def = CheckDefinition(
            name="positive_check",
            asset_key=AssetKey(name="my_asset"),
            fn=my_check,
        )
        result = run_check(check_def, 42)

        assert result.passed is True
        assert result.status == CheckStatus.PASSED
        assert result.check_name == "positive_check"
        assert result.duration_ms is not None

    def test_run_check_fails_bool(self):
        def my_check(value: int) -> bool:
            return value > 0

        check_def = CheckDefinition(
            name="positive_check",
            asset_key=AssetKey(name="my_asset"),
            fn=my_check,
        )
        result = run_check(check_def, -5)

        assert result.passed is False
        assert result.status == CheckStatus.FAILED

    def test_run_check_returns_check_result(self):
        def my_check(value: int) -> CheckResult:
            return CheckResult(
                passed=value > 0,
                check_name="positive_check",
                asset_key=AssetKey(name="my_asset"),
                status=CheckStatus.PASSED if value > 0 else CheckStatus.FAILED,
                metadata={"value": value},
            )

        check_def = CheckDefinition(
            name="positive_check",
            asset_key=AssetKey(name="my_asset"),
            fn=my_check,
        )
        result = run_check(check_def, 42)

        assert result.passed is True
        assert result.metadata["value"] == 42

    def test_run_check_error(self):
        def my_check(value: int) -> bool:
            raise ValueError("Intentional error")

        check_def = CheckDefinition(
            name="error_check",
            asset_key=AssetKey(name="my_asset"),
            fn=my_check,
        )
        result = run_check(check_def, 42)

        assert result.passed is False
        assert result.status == CheckStatus.ERROR
        assert "Intentional error" in result.error


class TestAssetWithChecks:
    """Tests for AssetWithChecks wrapper."""

    def test_asset_with_checks_delegation(self, registry: AssetRegistry):
        @asset(registry=registry)
        def my_asset() -> int:
            return 42

        # Should be an AssetWithChecks instance
        assert isinstance(my_asset, AssetWithChecks)

        # Should delegate properties
        assert my_asset.key.name == "my_asset"
        assert my_asset.return_type is int
        assert my_asset.dependencies == ()

        # Should be callable
        assert my_asset() == 42

    def test_check_decorator(self, registry: AssetRegistry):
        check_registry = CheckRegistry()

        @asset(registry=registry)
        def my_asset() -> int:
            return 42

        # Replace the default registry
        my_asset._registry = check_registry

        @my_asset.check
        def value_positive(value: int) -> bool:
            return value > 0

        checks = check_registry.get_checks(my_asset.key)
        assert len(checks) == 1
        assert checks[0].name == "value_positive"

    def test_check_decorator_with_args(self, registry: AssetRegistry):
        check_registry = CheckRegistry()

        @asset(registry=registry)
        def my_asset() -> int:
            return 42

        my_asset._registry = check_registry

        @my_asset.check(name="custom_name", description="Custom description")
        def my_check(value: int) -> bool:
            return value > 0

        checks = check_registry.get_checks(my_asset.key)
        assert len(checks) == 1
        assert checks[0].name == "custom_name"
        assert checks[0].description == "Custom description"

    def test_multiple_checks(self, registry: AssetRegistry):
        check_registry = CheckRegistry()

        @asset(registry=registry)
        def my_asset() -> int:
            return 42

        my_asset._registry = check_registry

        @my_asset.check
        def check1(value: int) -> bool:
            return value > 0

        @my_asset.check
        def check2(value: int) -> bool:
            return value < 100

        checks = check_registry.get_checks(my_asset.key)
        assert len(checks) == 2

    def test_asset_with_checks_hash(self, registry: AssetRegistry):
        @asset(registry=registry)
        def my_asset() -> int:
            return 42

        # Should be hashable
        s = {my_asset}
        assert my_asset in s


class TestRegisterCheck:
    """Tests for AssetWithChecks._register_check static method."""

    def test_custom_name_override(self) -> None:
        """Custom name overrides the function name."""
        registry = CheckRegistry()
        asset_key = AssetKey(name="my_asset")
        asset_def = AssetDefinition(
            key=asset_key,
            fn=lambda: 1,
            dependencies=(),
            dependency_params=(),
            return_type=int,
            description=None,
        )

        def my_check(value: int) -> bool:
            return value > 0

        AssetWithChecks._register_check(my_check, "custom_name", None, asset_def, registry)

        checks = registry.get_checks(asset_key)
        assert len(checks) == 1
        assert checks[0].name == "custom_name"

    def test_fallback_to_function_name(self) -> None:
        """When name is None, uses the function's __name__."""
        registry = CheckRegistry()
        asset_key = AssetKey(name="my_asset")
        asset_def = AssetDefinition(
            key=asset_key,
            fn=lambda: 1,
            dependencies=(),
            dependency_params=(),
            return_type=int,
            description=None,
        )

        def is_positive(value: int) -> bool:
            return value > 0

        AssetWithChecks._register_check(is_positive, None, None, asset_def, registry)

        checks = registry.get_checks(asset_key)
        assert len(checks) == 1
        assert checks[0].name == "is_positive"

    def test_docstring_as_description(self) -> None:
        """When description is None, uses the function's docstring."""
        registry = CheckRegistry()
        asset_key = AssetKey(name="my_asset")
        asset_def = AssetDefinition(
            key=asset_key,
            fn=lambda: 1,
            dependencies=(),
            dependency_params=(),
            return_type=int,
            description=None,
        )

        def my_check(value: int) -> bool:
            """Validates that value is positive."""
            return value > 0

        AssetWithChecks._register_check(my_check, None, None, asset_def, registry)

        checks = registry.get_checks(asset_key)
        assert len(checks) == 1
        assert checks[0].description == "Validates that value is positive."


class TestGlobalCheckRegistry:
    """Tests for global check registry."""

    def test_get_global_check_registry(self):
        reg1 = get_global_check_registry()
        reg2 = get_global_check_registry()
        assert reg1 is reg2
