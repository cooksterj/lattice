"""Tests for IO managers."""

import tempfile
from pathlib import Path

import pytest

from lattice import AssetKey
from lattice.io import FileIOManager, IOManager, MemoryIOManager


class TestMemoryIOManager:
    """Tests for MemoryIOManager."""

    def test_store_and_load(self) -> None:
        """Basic store and load."""
        io = MemoryIOManager()
        key = AssetKey(name="test")

        io.store(key, {"value": 42})
        result = io.load(key)

        assert result == {"value": 42}

    def test_load_missing_raises(self) -> None:
        """Loading nonexistent key raises KeyError."""
        io = MemoryIOManager()

        with pytest.raises(KeyError, match="test"):
            io.load(AssetKey(name="test"))

    def test_has(self) -> None:
        """Check existence with has()."""
        io = MemoryIOManager()
        key = AssetKey(name="test")

        assert not io.has(key)
        io.store(key, "value")
        assert io.has(key)

    def test_contains(self) -> None:
        """Check existence with 'in' operator."""
        io = MemoryIOManager()
        key = AssetKey(name="test")

        assert key not in io
        io.store(key, "value")
        assert key in io

    def test_delete(self) -> None:
        """Delete removes stored value."""
        io = MemoryIOManager()
        key = AssetKey(name="test")

        io.store(key, "value")
        assert io.has(key)

        io.delete(key)
        assert not io.has(key)

    def test_delete_nonexistent_is_noop(self) -> None:
        """Deleting nonexistent key does nothing."""
        io = MemoryIOManager()
        io.delete(AssetKey(name="nonexistent"))  # Should not raise

    def test_clear(self) -> None:
        """Clear removes all values."""
        io = MemoryIOManager()

        io.store(AssetKey(name="a"), 1)
        io.store(AssetKey(name="b"), 2)
        assert len(io) == 2

        io.clear()
        assert len(io) == 0

    def test_len(self) -> None:
        """Length returns number of stored assets."""
        io = MemoryIOManager()

        assert len(io) == 0
        io.store(AssetKey(name="a"), 1)
        assert len(io) == 1
        io.store(AssetKey(name="b"), 2)
        assert len(io) == 2

    def test_grouped_keys(self) -> None:
        """Keys with different groups are distinct."""
        io = MemoryIOManager()

        io.store(AssetKey(name="data", group="raw"), 1)
        io.store(AssetKey(name="data", group="processed"), 2)

        assert io.load(AssetKey(name="data", group="raw")) == 1
        assert io.load(AssetKey(name="data", group="processed")) == 2
        assert len(io) == 2

    def test_overwrite(self) -> None:
        """Storing with same key overwrites."""
        io = MemoryIOManager()
        key = AssetKey(name="test")

        io.store(key, "first")
        io.store(key, "second")

        assert io.load(key) == "second"
        assert len(io) == 1


class TestFileIOManager:
    """Tests for FileIOManager."""

    def test_store_and_load(self) -> None:
        """Basic store and load with pickle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            io = FileIOManager(tmpdir)
            key = AssetKey(name="test")

            io.store(key, {"value": 42})
            result = io.load(key)

            assert result == {"value": 42}

    def test_load_missing_raises(self) -> None:
        """Loading nonexistent key raises KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            io = FileIOManager(tmpdir)

            with pytest.raises(KeyError, match="test"):
                io.load(AssetKey(name="test"))

    def test_has(self) -> None:
        """Check existence with has()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            io = FileIOManager(tmpdir)
            key = AssetKey(name="test")

            assert not io.has(key)
            io.store(key, "value")
            assert io.has(key)

    def test_file_structure(self) -> None:
        """Files are organized by group."""
        with tempfile.TemporaryDirectory() as tmpdir:
            io = FileIOManager(tmpdir)

            io.store(AssetKey(name="data", group="raw"), 1)
            io.store(AssetKey(name="data", group="processed"), 2)

            base = Path(tmpdir)
            assert (base / "raw" / "data.pkl").exists()
            assert (base / "processed" / "data.pkl").exists()

    def test_delete(self) -> None:
        """Delete removes file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            io = FileIOManager(tmpdir)
            key = AssetKey(name="test")

            io.store(key, "value")
            assert io.has(key)

            io.delete(key)
            assert not io.has(key)

    def test_delete_nonexistent_is_noop(self) -> None:
        """Deleting nonexistent file does nothing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            io = FileIOManager(tmpdir)
            io.delete(AssetKey(name="nonexistent"))  # Should not raise

    def test_creates_directories(self) -> None:
        """IO manager creates base directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_path = Path(tmpdir) / "nested" / "path"
            FileIOManager(new_path)  # Creating the manager creates the directory

            assert new_path.exists()

    def test_grouped_keys(self) -> None:
        """Keys with different groups are distinct."""
        with tempfile.TemporaryDirectory() as tmpdir:
            io = FileIOManager(tmpdir)

            io.store(AssetKey(name="data", group="raw"), 1)
            io.store(AssetKey(name="data", group="processed"), 2)

            assert io.load(AssetKey(name="data", group="raw")) == 1
            assert io.load(AssetKey(name="data", group="processed")) == 2

    def test_complex_objects(self) -> None:
        """Store and load complex Python objects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            io = FileIOManager(tmpdir)
            key = AssetKey(name="complex")

            data = {
                "list": [1, 2, 3],
                "nested": {"a": {"b": {"c": 1}}},
                "tuple": (1, 2, 3),
                "set": {1, 2, 3},
            }
            io.store(key, data)
            result = io.load(key)

            assert result["list"] == [1, 2, 3]
            assert result["nested"]["a"]["b"]["c"] == 1
            assert result["tuple"] == (1, 2, 3)
            assert result["set"] == {1, 2, 3}

    def test_persistence_across_instances(self) -> None:
        """Data persists across IO manager instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key = AssetKey(name="persistent")

            io1 = FileIOManager(tmpdir)
            io1.store(key, "persisted_value")

            io2 = FileIOManager(tmpdir)
            assert io2.load(key) == "persisted_value"


class TestPartitionedStorage:
    """Tests for partition_key-scoped storage."""

    def test_memory_partition_isolation(self) -> None:
        """Same AssetKey with different partition_keys are independent."""
        io = MemoryIOManager()
        key = AssetKey(name="data", group="etl")

        io.store(key, "day1_value", partition_key="2026-04-05")
        io.store(key, "day2_value", partition_key="2026-04-06")

        assert io.load(key, partition_key="2026-04-05") == "day1_value"
        assert io.load(key, partition_key="2026-04-06") == "day2_value"

    def test_memory_no_partition_vs_partition_distinct(self) -> None:
        """partition_key=None and a real partition_key are separate slots."""
        io = MemoryIOManager()
        key = AssetKey(name="data")

        io.store(key, "unpartitioned")
        io.store(key, "partitioned", partition_key="2026-04-05")

        assert io.load(key) == "unpartitioned"
        assert io.load(key, partition_key="2026-04-05") == "partitioned"

    def test_memory_has_respects_partition(self) -> None:
        """has() returns False for unstored partition."""
        io = MemoryIOManager()
        key = AssetKey(name="data")

        io.store(key, "value", partition_key="2026-04-05")

        assert io.has(key, partition_key="2026-04-05")
        assert not io.has(key, partition_key="2026-04-06")
        assert not io.has(key)  # unpartitioned slot

    def test_memory_delete_respects_partition(self) -> None:
        """Deleting one partition doesn't affect another."""
        io = MemoryIOManager()
        key = AssetKey(name="data")

        io.store(key, "day1", partition_key="2026-04-05")
        io.store(key, "day2", partition_key="2026-04-06")

        io.delete(key, partition_key="2026-04-05")

        assert not io.has(key, partition_key="2026-04-05")
        assert io.has(key, partition_key="2026-04-06")
        assert io.load(key, partition_key="2026-04-06") == "day2"

    def test_file_partition_isolation(self) -> None:
        """FileIOManager stores partitioned data in separate subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            io = FileIOManager(tmpdir)
            key = AssetKey(name="data", group="etl")

            io.store(key, "day1_value", partition_key="2026-04-05")
            io.store(key, "day2_value", partition_key="2026-04-06")

            assert io.load(key, partition_key="2026-04-05") == "day1_value"
            assert io.load(key, partition_key="2026-04-06") == "day2_value"

    def test_file_partition_path_structure(self) -> None:
        """Verify {group}/{partition}/{name}.pkl layout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            io = FileIOManager(tmpdir)
            key = AssetKey(name="clean", group="etl")

            io.store(key, "value", partition_key="2026-04-05")

            base = Path(tmpdir)
            assert (base / "etl" / "2026-04-05" / "clean.pkl").exists()

    def test_file_backwards_compatible(self) -> None:
        """partition_key=None still uses {group}/{name}.pkl."""
        with tempfile.TemporaryDirectory() as tmpdir:
            io = FileIOManager(tmpdir)
            key = AssetKey(name="data", group="raw")

            io.store(key, "value")

            base = Path(tmpdir)
            assert (base / "raw" / "data.pkl").exists()
            # No partition subdirectory
            assert not (base / "raw" / "None").exists()


class TestIOManagerABC:
    """Tests for IOManager interface compliance."""

    def test_memory_implements_interface(self) -> None:
        """MemoryIOManager implements IOManager."""
        assert isinstance(MemoryIOManager(), IOManager)

    def test_file_implements_interface(self) -> None:
        """FileIOManager implements IOManager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            assert isinstance(FileIOManager(tmpdir), IOManager)

    def test_base_delete_raises(self) -> None:
        """Default delete() raises NotImplementedError."""

        # Create a minimal IOManager implementation
        class MinimalIOManager(IOManager):
            def load(self, key, annotation=None):
                pass

            def store(self, key, value):
                pass

            def has(self, key):
                return False

        io = MinimalIOManager()
        with pytest.raises(NotImplementedError, match="does not support deletion"):
            io.delete(AssetKey(name="test"))
