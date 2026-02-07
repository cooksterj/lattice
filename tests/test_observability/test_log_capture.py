"""Tests for log capture module."""

import logging

import pytest

from lattice import AssetKey
from lattice.observability.log_capture import ExecutionLogHandler, capture_logs


class TestExecutionLogHandler:
    """Tests for ExecutionLogHandler."""

    def test_captures_log_entries(self):
        handler = ExecutionLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("test_handler")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        try:
            logger.info("Test message")
            logger.warning("Warning message")

            entries = handler.entries
            assert len(entries) == 2
            assert entries[0].message == "Test message"
            assert entries[0].level == "INFO"
            assert entries[1].message == "Warning message"
            assert entries[1].level == "WARNING"
        finally:
            logger.removeHandler(handler)

    def test_tracks_current_asset(self):
        handler = ExecutionLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("test_asset_tracking")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        try:
            logger.info("Before asset")

            handler.set_current_asset(AssetKey(name="my_asset"))
            logger.info("During asset")

            handler.set_current_asset(None)
            logger.info("After asset")

            entries = handler.entries
            assert entries[0].asset_key is None
            assert entries[1].asset_key.name == "my_asset"
            assert entries[2].asset_key is None
        finally:
            logger.removeHandler(handler)

    def test_entries_returns_copy(self):
        handler = ExecutionLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("test_copy")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        try:
            logger.info("Test")

            entries1 = handler.entries
            entries2 = handler.entries
            assert entries1 is not entries2
        finally:
            logger.removeHandler(handler)

    def test_clear(self):
        handler = ExecutionLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.set_current_asset(AssetKey(name="test"))

        logger = logging.getLogger("test_clear")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        try:
            logger.info("Test")
            assert len(handler.entries) == 1

            handler.clear()
            assert len(handler.entries) == 0
        finally:
            logger.removeHandler(handler)

    def test_emit_calls_on_entry_callback(self):
        received: list = []
        handler = ExecutionLogHandler(on_entry=lambda entry: received.append(entry))
        handler.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("test_on_entry")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        try:
            logger.info("Callback test")

            assert len(received) == 1
            assert received[0].message == "Callback test"
            assert received[0].level == "INFO"
        finally:
            logger.removeHandler(handler)

    def test_emit_no_callback_by_default(self):
        handler = ExecutionLogHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("test_no_callback")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        try:
            logger.info("No callback")
            assert len(handler.entries) == 1
        finally:
            logger.removeHandler(handler)

    def test_on_entry_callback_receives_asset_context(self):
        received: list = []
        handler = ExecutionLogHandler(on_entry=lambda entry: received.append(entry))
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.set_current_asset(AssetKey(name="my_asset"))

        logger = logging.getLogger("test_callback_asset")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        try:
            logger.info("With asset context")

            assert len(received) == 1
            assert received[0].asset_key is not None
            assert received[0].asset_key.name == "my_asset"
        finally:
            logger.removeHandler(handler)


class TestCaptureLogs:
    """Tests for capture_logs context manager."""

    def test_captures_lattice_logs(self):
        logger = logging.getLogger("lattice")
        original_level = logger.level

        # Set logger level to INFO to ensure logs are captured
        logger.setLevel(logging.INFO)

        try:
            with capture_logs() as handler:
                logger.info("Test message from lattice")

            entries = handler.entries
            assert len(entries) >= 1
            assert any("Test message from lattice" in e.message for e in entries)
        finally:
            # Restore original level
            logger.setLevel(original_level)

    def test_captures_sublogs(self):
        logger = logging.getLogger("lattice.executor")
        logger.setLevel(logging.INFO)

        with capture_logs("lattice") as handler:
            logger.info("From sublogs")

        entries = handler.entries
        assert any("From sublogs" in e.message for e in entries)

    def test_captures_at_specified_level(self):
        with capture_logs(level=logging.WARNING) as handler:
            logger = logging.getLogger("lattice")
            logger.debug("Debug message")
            logger.warning("Warning message")

        entries = handler.entries
        # Should not capture DEBUG when level is WARNING
        assert not any("Debug message" in e.message for e in entries)
        assert any("Warning message" in e.message for e in entries)

    def test_handler_removed_after_context(self):
        logger = logging.getLogger("lattice")
        initial_handler_count = len(logger.handlers)

        with capture_logs():
            assert len(logger.handlers) == initial_handler_count + 1

        assert len(logger.handlers) == initial_handler_count

    def test_handler_removed_on_exception(self):
        logger = logging.getLogger("lattice")
        initial_handler_count = len(logger.handlers)

        with pytest.raises(ValueError), capture_logs():
            raise ValueError("Test error")

        assert len(logger.handlers) == initial_handler_count

    def test_can_set_current_asset(self):
        logger = logging.getLogger("lattice")
        logger.setLevel(logging.INFO)

        with capture_logs() as handler:
            handler.set_current_asset(AssetKey(name="test_asset"))
            logger.info("Message with asset context")
            handler.set_current_asset(None)

        entries = handler.entries
        asset_entries = [e for e in entries if e.asset_key is not None]
        assert len(asset_entries) >= 1
        assert asset_entries[0].asset_key.name == "test_asset"

    def test_capture_logs_with_on_entry_callback(self):
        received: list = []
        logger = logging.getLogger("lattice")
        logger.setLevel(logging.INFO)

        with capture_logs(on_entry=lambda entry: received.append(entry)):
            logger.info("Callback via capture_logs")

        assert len(received) >= 1
        assert any("Callback via capture_logs" in e.message for e in received)
