"""
Pydantic models for dbt manifest data.

This module defines data models for representing dbt models
extracted from a dbt manifest.json file.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DbtModelInfo(BaseModel):
    """
    Metadata for a single dbt model extracted from manifest.json.

    Attributes
    ----------
    unique_id : str
        The dbt unique identifier (e.g., "model.project.model_name").
    name : str
        The model name.
    description : str or None
        Optional model description.
    materialization : str
        The materialization strategy (table, view, incremental).
    schema_name : str or None
        The target schema for the model.
    database : str or None
        The target database for the model.
    depends_on : tuple of str
        Unique IDs of upstream model dependencies (only model refs, not sources).
    tags : tuple of str
        Tags associated with this model.
    """

    model_config = ConfigDict(frozen=True)

    unique_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str | None = None
    materialization: str = Field(default="table")
    schema_name: str | None = None
    database: str | None = None
    depends_on: tuple[str, ...] = Field(default_factory=tuple)
    tags: tuple[str, ...] = Field(default_factory=tuple)
