"""
Custom exceptions for the Lattice orchestration framework.

This module defines domain-specific exceptions raised during dependency
graph construction, validation, and execution planning.
"""

from typing import TYPE_CHECKING

# TYPE_CHECKING is True only during static analysis (mypy/pyright), False at runtime.
# This pattern:
#   1. Avoids circular imports - the import doesn't execute at runtime
#   2. Enables type hints - type checkers still see the import
#   3. Requires forward references - use quotes like "AssetKey" in annotations
if TYPE_CHECKING:
    from lattice.models import AssetKey


class CyclicDependencyError(Exception):
    """
    Raised when a cycle is detected in the dependency graph.

    Attributes
    ----------
    cycle : list of AssetKey
        The cycle path, e.g., [A, B, C, A] where A depends on C,
        C depends on B, and B depends on A.
    """

    def __init__(self, cycle: list["AssetKey"]) -> None:
        """
        Initialize the exception with the cycle path.

        Parameters
        ----------
        cycle : list of AssetKey
            The detected cycle, including the repeated node at the end.
        """
        self.cycle = cycle
        cycle_str = " -> ".join(str(key) for key in cycle)
        super().__init__(f"Cyclic dependency detected: {cycle_str}")
