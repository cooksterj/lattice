"""Shared pytest fixtures for Lattice tests."""

import pytest

from lattice import AssetRegistry, get_global_check_registry, get_global_registry


@pytest.fixture(autouse=True)
def clean_global_registries() -> None:
    """Clear global registries before each test."""
    get_global_registry().clear()
    get_global_check_registry().clear()


@pytest.fixture
def registry() -> AssetRegistry:
    """Provide a fresh isolated registry for testing."""
    return AssetRegistry()
