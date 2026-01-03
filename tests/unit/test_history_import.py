"""Tests for historical energy import functionality."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.intuis_connect.history_import import (
    _get_existing_statistics,
    _fix_statistics_discontinuity,
    DISCONTINUITY_THRESHOLD,
)


class TestGetExistingStatistics:
    """Tests for _get_existing_statistics helper."""

    @pytest.mark.asyncio
    async def test_returns_statistics_for_entity(self):
        """Should return statistics from statistics_during_period."""
        mock_hass = MagicMock()
        mock_stats = [
            {"start": 1704067200, "state": 5.0, "sum": 100.0},
            {"start": 1704153600, "state": 6.0, "sum": 106.0},
        ]

        with patch(
            "custom_components.intuis_connect.history_import.statistics_during_period",
            return_value={"sensor.energy": mock_stats},
        ):
            mock_hass.async_add_executor_job = AsyncMock(
                return_value={"sensor.energy": mock_stats}
            )

            result = await _get_existing_statistics(
                mock_hass,
                "sensor.energy",
                datetime(2024, 1, 1, tzinfo=timezone.utc),
            )

        assert result == mock_stats

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_no_data(self):
        """Should return empty list when no statistics found."""
        mock_hass = MagicMock()
        mock_hass.async_add_executor_job = AsyncMock(return_value={})

        result = await _get_existing_statistics(
            mock_hass,
            "sensor.energy",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_exception(self):
        """Should return empty list and log warning on exception."""
        mock_hass = MagicMock()
        mock_hass.async_add_executor_job = AsyncMock(side_effect=Exception("DB error"))

        result = await _get_existing_statistics(
            mock_hass,
            "sensor.energy",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        assert result == []


class TestFixStatisticsDiscontinuity:
    """Tests for _fix_statistics_discontinuity function."""

    @pytest.fixture
    def mock_metadata(self):
        """Create mock StatisticMetaData."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_no_existing_stats_returns_zero(self, mock_metadata):
        """Should return 0 when no existing statistics after import."""
        mock_hass = MagicMock()

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await _fix_statistics_discontinuity(
                hass=mock_hass,
                entity_id="sensor.energy",
                room_name="Living Room",
                import_end_time=datetime(2025, 11, 30, tzinfo=timezone.utc),
                import_end_sum=2833.0,
                metadata=mock_metadata,
            )

        assert result == 0

    @pytest.mark.asyncio
    async def test_no_discontinuity_returns_zero(self, mock_metadata):
        """Should return 0 when statistics are already aligned."""
        mock_hass = MagicMock()

        # Existing stats that continue properly from import
        # import_end_sum = 2833, first_existing_state = 8, first_existing_sum = 2841
        # expected = 2833 + 8 = 2841, discontinuity = 2841 - 2841 = 0
        existing_stats = [
            {"start": 1733011200, "state": 8.0, "sum": 2841.0},  # Dec 1
            {"start": 1733097600, "state": 7.0, "sum": 2848.0},  # Dec 2
        ]

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=existing_stats,
        ):
            result = await _fix_statistics_discontinuity(
                hass=mock_hass,
                entity_id="sensor.energy",
                room_name="Living Room",
                import_end_time=datetime(2025, 11, 30, tzinfo=timezone.utc),
                import_end_sum=2833.0,
                metadata=mock_metadata,
            )

        assert result == 0

    @pytest.mark.asyncio
    async def test_detects_and_fixes_discontinuity(self, mock_metadata):
        """Should detect discontinuity and adjust statistics."""
        mock_hass = MagicMock()

        # Simulating the user's issue:
        # import_end_sum = 2833 (end of historical import)
        # Live data has its own baseline: first_state = 8, first_sum = 8
        # Expected: 2833 + 8 = 2841
        # Actual: 8
        # Discontinuity: 2841 - 8 = 2833
        existing_stats = [
            {"start": 1733011200, "state": 8.0, "sum": 8.0},    # Dec 1 - wrong sum
            {"start": 1733097600, "state": 7.0, "sum": 15.0},   # Dec 2 - wrong sum
            {"start": 1733184000, "state": 9.0, "sum": 24.0},   # Dec 3 - wrong sum
        ]

        import_calls = []

        def capture_import(hass, metadata, statistics):
            import_calls.append(statistics)

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=existing_stats,
        ), patch(
            "custom_components.intuis_connect.history_import.async_import_statistics",
            side_effect=capture_import,
        ):
            result = await _fix_statistics_discontinuity(
                hass=mock_hass,
                entity_id="sensor.energy",
                room_name="Living Room",
                import_end_time=datetime(2025, 11, 30, tzinfo=timezone.utc),
                import_end_sum=2833.0,
                metadata=mock_metadata,
            )

        assert result == 3  # Adjusted 3 entries
        assert len(import_calls) == 1

        adjusted = import_calls[0]
        assert len(adjusted) == 3

        # Check that sums were adjusted by the discontinuity amount (2833)
        # First entry: 8 + 2833 = 2841
        assert adjusted[0]["sum"] == 8.0 + 2833.0
        # Second entry: 15 + 2833 = 2848
        assert adjusted[1]["sum"] == 15.0 + 2833.0
        # Third entry: 24 + 2833 = 2857
        assert adjusted[2]["sum"] == 24.0 + 2833.0

        # States should remain unchanged
        assert adjusted[0]["state"] == 8.0
        assert adjusted[1]["state"] == 7.0
        assert adjusted[2]["state"] == 9.0

    @pytest.mark.asyncio
    async def test_threshold_prevents_tiny_adjustments(self, mock_metadata):
        """Should not adjust if discontinuity is below threshold."""
        mock_hass = MagicMock()

        # Small discontinuity of 0.5 kWh (below DISCONTINUITY_THRESHOLD of 1.0)
        existing_stats = [
            {"start": 1733011200, "state": 8.0, "sum": 2840.5},  # 0.5 kWh off
        ]

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=existing_stats,
        ):
            result = await _fix_statistics_discontinuity(
                hass=mock_hass,
                entity_id="sensor.energy",
                room_name="Living Room",
                import_end_time=datetime(2025, 11, 30, tzinfo=timezone.utc),
                import_end_sum=2833.0,
                metadata=mock_metadata,
            )

        assert result == 0  # No adjustment made

    @pytest.mark.asyncio
    async def test_handles_timestamp_as_float(self, mock_metadata):
        """Should handle timestamps as floats (epoch seconds)."""
        mock_hass = MagicMock()

        existing_stats = [
            {"start": 1733011200.0, "state": 8.0, "sum": 8.0},  # Float timestamp
        ]

        import_calls = []

        def capture_import(hass, metadata, statistics):
            import_calls.append(statistics)

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=existing_stats,
        ), patch(
            "custom_components.intuis_connect.history_import.async_import_statistics",
            side_effect=capture_import,
        ):
            result = await _fix_statistics_discontinuity(
                hass=mock_hass,
                entity_id="sensor.energy",
                room_name="Living Room",
                import_end_time=datetime(2025, 11, 30, tzinfo=timezone.utc),
                import_end_sum=2833.0,
                metadata=mock_metadata,
            )

        assert result == 1
        # Check that the timestamp was properly converted to datetime
        adjusted = import_calls[0][0]
        assert isinstance(adjusted["start"], datetime)

    @pytest.mark.asyncio
    async def test_handles_none_values(self, mock_metadata):
        """Should handle None values in statistics gracefully."""
        mock_hass = MagicMock()

        existing_stats = [
            {"start": 1733011200, "state": None, "sum": None},  # None values
        ]

        import_calls = []

        def capture_import(hass, metadata, statistics):
            import_calls.append(statistics)

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=existing_stats,
        ), patch(
            "custom_components.intuis_connect.history_import.async_import_statistics",
            side_effect=capture_import,
        ):
            result = await _fix_statistics_discontinuity(
                hass=mock_hass,
                entity_id="sensor.energy",
                room_name="Living Room",
                import_end_time=datetime(2025, 11, 30, tzinfo=timezone.utc),
                import_end_sum=2833.0,
                metadata=mock_metadata,
            )

        assert result == 1
        adjusted = import_calls[0][0]
        assert adjusted["state"] == 0  # None converted to 0
        assert adjusted["sum"] == 2833.0  # 0 + 2833

    @pytest.mark.asyncio
    async def test_reimport_does_not_double_adjust(self, mock_metadata):
        """Re-importing should not double-adjust already fixed statistics."""
        mock_hass = MagicMock()

        # After first import+fix, sums are correct
        # If user reimports, the discontinuity should be ~0
        existing_stats = [
            {"start": 1733011200, "state": 8.0, "sum": 2841.0},  # Already adjusted
            {"start": 1733097600, "state": 7.0, "sum": 2848.0},
        ]

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=existing_stats,
        ):
            result = await _fix_statistics_discontinuity(
                hass=mock_hass,
                entity_id="sensor.energy",
                room_name="Living Room",
                import_end_time=datetime(2025, 11, 30, tzinfo=timezone.utc),
                import_end_sum=2833.0,  # Same import sum as before
                metadata=mock_metadata,
            )

        # Discontinuity = (2833 + 8) - 2841 = 0, no adjustment needed
        assert result == 0
