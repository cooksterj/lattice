"""Tests for dbt Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lattice.dbt.models import DbtModelInfo


class TestDbtModelInfo:
    """Tests for the DbtModelInfo frozen model."""

    def test_create_minimal(self) -> None:
        """Create a model with only required fields."""
        model = DbtModelInfo(
            unique_id="model.proj.foo",
            name="foo",
        )
        assert model.unique_id == "model.proj.foo"
        assert model.name == "foo"
        assert model.description is None
        assert model.materialization == "table"
        assert model.schema_name is None
        assert model.database is None
        assert model.depends_on == ()
        assert model.tags == ()

    def test_create_full(self) -> None:
        """Create a model with all fields populated."""
        model = DbtModelInfo(
            unique_id="model.proj.bar",
            name="bar",
            description="A bar model",
            materialization="view",
            schema_name="staging",
            database="analytics",
            depends_on=("model.proj.foo",),
            tags=("core", "v2"),
        )
        assert model.description == "A bar model"
        assert model.materialization == "view"
        assert model.schema_name == "staging"
        assert model.database == "analytics"
        assert model.depends_on == ("model.proj.foo",)
        assert model.tags == ("core", "v2")

    def test_frozen(self) -> None:
        """DbtModelInfo should be immutable."""
        model = DbtModelInfo(unique_id="model.proj.x", name="x")
        with pytest.raises(ValidationError):
            model.name = "y"  # type: ignore[misc]

    def test_equality(self) -> None:
        """Two models with same fields should be equal."""
        a = DbtModelInfo(unique_id="model.proj.x", name="x")
        b = DbtModelInfo(unique_id="model.proj.x", name="x")
        assert a == b

    def test_inequality(self) -> None:
        """Models with different fields should not be equal."""
        a = DbtModelInfo(unique_id="model.proj.x", name="x")
        b = DbtModelInfo(unique_id="model.proj.y", name="y")
        assert a != b
