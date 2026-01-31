"""IO managers for asset storage.

This module provides storage backends for loading and storing
materialized assets. Available managers:

- ``MemoryIOManager``: In-memory storage for testing
- ``FileIOManager``: Pickle-based file storage
- ``ParquetIOManager``: Parquet storage for DataFrames
"""

from lattice.io.base import IOManager
from lattice.io.file import FileIOManager
from lattice.io.memory import MemoryIOManager
from lattice.io.parquet import ParquetIOManager

__all__ = [
    "IOManager",
    "FileIOManager",
    "MemoryIOManager",
    "ParquetIOManager",
]
