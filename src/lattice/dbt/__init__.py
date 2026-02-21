"""
dbt integration for Lattice.

This module provides tools for loading dbt manifest.json files and
registering dbt models as Lattice assets with their dependency graph intact.
"""

from lattice.dbt.assets import DBT_GROUP, dbt_assets, load_dbt_manifest
from lattice.dbt.manifest import ManifestParser
from lattice.dbt.models import DbtModelInfo

__all__ = [
    "DBT_GROUP",
    "DbtModelInfo",
    "ManifestParser",
    "dbt_assets",
    "load_dbt_manifest",
]
