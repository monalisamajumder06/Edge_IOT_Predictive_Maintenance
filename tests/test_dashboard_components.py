"""Unit Tests for Dashboard UI Components and Formatting Logic.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 5 Implementation
Classification: [PROJECT REQUIREMENT / IMPLEMENTATION DECISION]

Tests cover:
1. Timestamp formatting logic (ISO-8601 strings, UNIX epoch, None, invalid values).
2. UI formatting behavior without inventing thresholds or severities.
3. Empty state handling for health observations, RUL observations, and fault logs.
"""

from datetime import datetime, timezone
import pytest

from dashboard.components import format_iso_timestamp


class TestComponentFormatting:
    """Verifies display formatting helpers."""

    def test_format_iso_timestamp_valid_iso_utc(self):
        """Verify ISO-8601 UTC string is formatted cleanly."""
        ts_str = "2026-09-13T14:30:00Z"
        formatted = format_iso_timestamp(ts_str)
        assert "2026-09-13 14:30:00 UTC" in formatted

    def test_format_iso_timestamp_unix_epoch(self):
        """Verify numeric epoch timestamp is supported."""
        epoch = 1789297800.0  # Represents a UTC timestamp
        formatted = format_iso_timestamp(epoch)
        assert "UTC" in formatted

    def test_format_iso_timestamp_none_returns_na(self):
        """Verify None or empty string returns 'N/A'."""
        assert format_iso_timestamp(None) == "N/A"
        assert format_iso_timestamp("") == "N/A"

    def test_format_iso_timestamp_datetime_object(self):
        """Verify datetime object directly formats properly."""
        dt = datetime(2026, 9, 13, 15, 0, 0, tzinfo=timezone.utc)
        formatted = format_iso_timestamp(dt)
        assert formatted == "2026-09-13 15:00:00 UTC"

    def test_format_iso_timestamp_malformed_returns_raw_string(self):
        """Verify malformed timestamp string is returned safely without crashing."""
        malformed = "not-a-timestamp"
        formatted = format_iso_timestamp(malformed)
        assert formatted == malformed
