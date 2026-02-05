"""Tests for lineage tracking module."""

from lattice import AssetKey, MemoryIOManager
from lattice.observability.lineage import LineageIOManager, LineageTracker


class TestLineageTracker:
    """Tests for LineageTracker."""

    def test_record_read(self):
        tracker = LineageTracker()
        tracker.record_read(AssetKey(name="source"))

        events = tracker.events
        assert len(events) == 1
        assert events[0].event_type == "read"
        assert events[0].asset_key.name == "source"
        assert events[0].source_asset is None

    def test_record_write(self):
        tracker = LineageTracker()
        tracker.record_write(AssetKey(name="output"))

        events = tracker.events
        assert len(events) == 1
        assert events[0].event_type == "write"
        assert events[0].asset_key.name == "output"

    def test_tracks_current_asset(self):
        tracker = LineageTracker()
        tracker.set_current_asset(AssetKey(name="transform"))
        tracker.record_read(AssetKey(name="source"))

        events = tracker.events
        assert events[0].source_asset.name == "transform"

    def test_record_with_metadata(self):
        tracker = LineageTracker()
        tracker.record_write(AssetKey(name="output"), metadata={"rows": 100})

        events = tracker.events
        assert events[0].metadata["rows"] == 100

    def test_events_returns_copy(self):
        tracker = LineageTracker()
        tracker.record_read(AssetKey(name="source"))

        events1 = tracker.events
        events2 = tracker.events
        assert events1 is not events2

    def test_clear(self):
        tracker = LineageTracker()
        tracker.set_current_asset(AssetKey(name="test"))
        tracker.record_read(AssetKey(name="source"))

        tracker.clear()
        assert len(tracker.events) == 0

    def test_multiple_events(self):
        tracker = LineageTracker()
        tracker.set_current_asset(AssetKey(name="transform"))
        tracker.record_read(AssetKey(name="source1"))
        tracker.record_read(AssetKey(name="source2"))
        tracker.record_write(AssetKey(name="output"))

        events = tracker.events
        assert len(events) == 3
        assert events[0].event_type == "read"
        assert events[1].event_type == "read"
        assert events[2].event_type == "write"


class TestLineageIOManager:
    """Tests for LineageIOManager."""

    def test_records_loads_as_reads(self):
        base_io = MemoryIOManager()
        base_io.store(AssetKey(name="source"), {"value": 42})

        tracker = LineageTracker()
        lineage_io = LineageIOManager(base_io, tracker)

        value = lineage_io.load(AssetKey(name="source"))
        assert value == {"value": 42}

        events = tracker.events
        assert len(events) == 1
        assert events[0].event_type == "read"
        assert events[0].asset_key.name == "source"

    def test_records_stores_as_writes(self):
        base_io = MemoryIOManager()
        tracker = LineageTracker()
        lineage_io = LineageIOManager(base_io, tracker)

        lineage_io.store(AssetKey(name="output"), {"value": 42})

        events = tracker.events
        assert len(events) == 1
        assert events[0].event_type == "write"
        assert events[0].asset_key.name == "output"

        # Verify the value was actually stored
        assert base_io.load(AssetKey(name="output")) == {"value": 42}

    def test_tracks_current_asset_on_reads(self):
        base_io = MemoryIOManager()
        base_io.store(AssetKey(name="source"), {"value": 42})

        tracker = LineageTracker()
        tracker.set_current_asset(AssetKey(name="transform"))
        lineage_io = LineageIOManager(base_io, tracker)

        lineage_io.load(AssetKey(name="source"))

        events = tracker.events
        assert events[0].source_asset.name == "transform"

    def test_has_delegates_to_wrapped(self):
        base_io = MemoryIOManager()
        base_io.store(AssetKey(name="existing"), 42)

        tracker = LineageTracker()
        lineage_io = LineageIOManager(base_io, tracker)

        assert lineage_io.has(AssetKey(name="existing")) is True
        assert lineage_io.has(AssetKey(name="nonexistent")) is False

    def test_delete_delegates_to_wrapped(self):
        base_io = MemoryIOManager()
        base_io.store(AssetKey(name="to_delete"), 42)

        tracker = LineageTracker()
        lineage_io = LineageIOManager(base_io, tracker)

        lineage_io.delete(AssetKey(name="to_delete"))
        assert not base_io.has(AssetKey(name="to_delete"))

    def test_tracker_property(self):
        base_io = MemoryIOManager()
        tracker = LineageTracker()
        lineage_io = LineageIOManager(base_io, tracker)

        assert lineage_io.tracker is tracker

    def test_wrapped_property(self):
        base_io = MemoryIOManager()
        tracker = LineageTracker()
        lineage_io = LineageIOManager(base_io, tracker)

        assert lineage_io.wrapped is base_io

    def test_full_lineage_chain(self):
        """Test tracking a full asset execution chain."""
        base_io = MemoryIOManager()
        tracker = LineageTracker()
        lineage_io = LineageIOManager(base_io, tracker)

        # Simulate: source -> transform -> output
        # First, create source data
        lineage_io.store(AssetKey(name="source"), [1, 2, 3])

        # Transform reads source and writes output
        tracker.set_current_asset(AssetKey(name="transform"))
        source_data = lineage_io.load(AssetKey(name="source"))
        transformed = [x * 2 for x in source_data]
        lineage_io.store(AssetKey(name="transform"), transformed)

        tracker.set_current_asset(None)

        events = tracker.events
        assert len(events) == 3

        # First write (source)
        assert events[0].event_type == "write"
        assert events[0].asset_key.name == "source"

        # Read during transform
        assert events[1].event_type == "read"
        assert events[1].asset_key.name == "source"
        assert events[1].source_asset.name == "transform"

        # Write from transform
        assert events[2].event_type == "write"
        assert events[2].asset_key.name == "transform"
