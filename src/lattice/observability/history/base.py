"""Abstract base class for run history storage."""

from abc import ABC, abstractmethod

from lattice.observability.models import RunRecord


class RunHistoryStore(ABC):
    """
    Abstract base class for run history storage.

    Implementations store and retrieve run records for historical
    analysis and debugging.
    """

    @abstractmethod
    def save(self, record: RunRecord) -> None:
        """
        Save a run record.

        Parameters
        ----------
        record : RunRecord
            The run record to save.
        """
        ...

    @abstractmethod
    def get(self, run_id: str) -> RunRecord | None:
        """
        Get a run record by ID.

        Parameters
        ----------
        run_id : str
            The run ID to look up.

        Returns
        -------
        RunRecord or None
            The run record if found, None otherwise.
        """
        ...

    @abstractmethod
    def list_runs(
        self,
        limit: int = 50,
        status: str | None = None,
        offset: int = 0,
    ) -> list[RunRecord]:
        """
        List run records with optional filtering.

        Parameters
        ----------
        limit : int
            Maximum number of records to return.
        status : str or None
            Filter by status if provided.
        offset : int
            Number of records to skip for pagination.

        Returns
        -------
        list of RunRecord
            Matching run records, ordered by start time descending.
        """
        ...

    @abstractmethod
    def delete(self, run_id: str) -> bool:
        """
        Delete a run record.

        Parameters
        ----------
        run_id : str
            The run ID to delete.

        Returns
        -------
        bool
            True if the record was deleted, False if not found.
        """
        ...

    def count(self, status: str | None = None) -> int:
        """
        Count run records with optional status filter.

        Parameters
        ----------
        status : str or None
            Filter by status if provided.

        Returns
        -------
        int
            Number of matching records.
        """
        # Default implementation - subclasses may override for efficiency
        return len(self.list_runs(limit=10000, status=status))

    def clear(self) -> int:
        """
        Delete all run records.

        Returns
        -------
        int
            Number of records deleted.
        """
        records = self.list_runs(limit=10000)
        count = 0
        for record in records:
            if self.delete(record.run_id):
                count += 1
        return count
