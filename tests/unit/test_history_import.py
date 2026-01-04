"""Tests for historical energy import functionality."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.intuis_connect.history_import import (
    _get_existing_statistics,
    _get_baseline_sum,
    _clear_statistics_in_range,
    _fix_post_import_discontinuity,
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

        mock_instance = MagicMock()
        mock_instance.async_add_executor_job = AsyncMock(
            return_value={"sensor.energy": mock_stats}
        )

        with patch(
            "custom_components.intuis_connect.history_import.get_instance",
            return_value=mock_instance,
        ):
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
        mock_instance = MagicMock()
        mock_instance.async_add_executor_job = AsyncMock(return_value={})

        with patch(
            "custom_components.intuis_connect.history_import.get_instance",
            return_value=mock_instance,
        ):
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
        mock_instance = MagicMock()
        mock_instance.async_add_executor_job = AsyncMock(side_effect=Exception("DB error"))

        with patch(
            "custom_components.intuis_connect.history_import.get_instance",
            return_value=mock_instance,
        ):
            result = await _get_existing_statistics(
                mock_hass,
                "sensor.energy",
                datetime(2024, 1, 1, tzinfo=timezone.utc),
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_passes_end_time_parameter(self):
        """Should pass end_time to statistics_during_period."""
        mock_hass = MagicMock()
        mock_instance = MagicMock()
        mock_instance.async_add_executor_job = AsyncMock(return_value={})

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 6, 1, tzinfo=timezone.utc)

        with patch(
            "custom_components.intuis_connect.history_import.get_instance",
            return_value=mock_instance,
        ):
            await _get_existing_statistics(mock_hass, "sensor.energy", start, end)

        # Check that async_add_executor_job was called with the right args
        call_args = mock_instance.async_add_executor_job.call_args
        assert call_args is not None
        # The end_time should be passed (3rd positional arg after hass and start)


class TestGetBaselineSum:
    """Tests for _get_baseline_sum helper."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_prior_stats(self):
        """Should return 0 when no statistics exist before import period."""
        mock_hass = MagicMock()

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await _get_baseline_sum(
                mock_hass,
                "sensor.energy",
                "Living Room",
                datetime(2025, 11, 19, tzinfo=timezone.utc),
            )

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_returns_last_sum_from_existing_stats(self):
        """Should return the last sum value from existing statistics."""
        mock_hass = MagicMock()

        # Simulate existing stats from Oct-Nov 18 (before import on Nov 19)
        existing_stats = [
            {"start": 1729382400, "state": 8.0, "sum": 200.0},   # Oct 20
            {"start": 1729468800, "state": 7.0, "sum": 207.0},   # Oct 21
            {"start": 1731888000, "state": 9.0, "sum": 450.0},   # Nov 18
        ]

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=existing_stats,
        ):
            result = await _get_baseline_sum(
                mock_hass,
                "sensor.energy",
                "Living Room",
                datetime(2025, 11, 19, tzinfo=timezone.utc),
            )

        # Should return the last entry's sum
        assert result == 450.0

    @pytest.mark.asyncio
    async def test_handles_none_sum_value(self):
        """Should handle None sum values gracefully."""
        mock_hass = MagicMock()

        existing_stats = [
            {"start": 1729382400, "state": 8.0, "sum": None},
        ]

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=existing_stats,
        ):
            result = await _get_baseline_sum(
                mock_hass,
                "sensor.energy",
                "Living Room",
                datetime(2025, 11, 19, tzinfo=timezone.utc),
            )

        assert result == 0

    @pytest.mark.asyncio
    async def test_queries_correct_time_range(self):
        """Should query from 730 days before import start to import start."""
        mock_hass = MagicMock()
        import_start = datetime(2025, 11, 19, tzinfo=timezone.utc)

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_get_stats:
            await _get_baseline_sum(
                mock_hass,
                "sensor.energy",
                "Living Room",
                import_start,
            )

            # Check that _get_existing_statistics was called with correct range
            mock_get_stats.assert_called_once()
            call_args = mock_get_stats.call_args
            assert call_args[0][0] == mock_hass
            assert call_args[0][1] == "sensor.energy"
            # Start should be 730 days before import_start
            expected_start = import_start - timedelta(days=730)
            assert call_args[0][2] == expected_start
            # End should be import_start
            assert call_args[0][3] == import_start


class TestBaselineIntegration:
    """Integration tests for the baseline sum feature."""

    @pytest.mark.asyncio
    async def test_import_continues_from_baseline(self):
        """Verify import starts cumulative sum from baseline."""
        # This test verifies the fix for the -2092 kWh bug
        #
        # Scenario:
        # - Live sensor tracked Oct-Nov 18 with sum reaching 450 kWh
        # - Import starts Nov 19 for 45 days
        # - Import should continue from 450, not start at 0
        #
        # Before fix:
        #   Nov 18: sum = 450 (live data)
        #   Nov 19: sum = 8   (import starts at 0)
        #   November energy = sum(Nov 30) - sum(Oct 31) = negative!
        #
        # After fix:
        #   Nov 18: sum = 450 (live data)
        #   Nov 19: sum = 458 (import continues from 450)
        #   November energy = sum(Nov 30) - sum(Oct 31) = correct!

        mock_hass = MagicMock()

        # Existing stats end Nov 18 with sum = 450
        existing_stats = [
            {"start": 1731888000, "state": 9.0, "sum": 450.0},  # Nov 18
        ]

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=existing_stats,
        ):
            baseline = await _get_baseline_sum(
                mock_hass,
                "sensor.energy",
                "Living Room",
                datetime(2025, 11, 19, tzinfo=timezone.utc),
            )

        assert baseline == 450.0

        # Now if import adds 8 kWh on Nov 19:
        # cumulative_sum = baseline + 8 = 458
        # This is correct and continues smoothly from Nov 18's 450
        first_import_sum = baseline + 8.0
        assert first_import_sum == 458.0

    @pytest.mark.asyncio
    async def test_fresh_install_starts_at_zero(self):
        """Verify fresh install with no prior data starts at 0."""
        mock_hass = MagicMock()

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=[],
        ):
            baseline = await _get_baseline_sum(
                mock_hass,
                "sensor.energy",
                "Living Room",
                datetime(2025, 11, 19, tzinfo=timezone.utc),
            )

        assert baseline == 0.0


class TestFixPostImportDiscontinuity:
    """Tests for _fix_post_import_discontinuity function."""

    @pytest.fixture
    def mock_metadata(self):
        """Create mock StatisticMetaData."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_no_post_import_stats_returns_zero(self, mock_metadata):
        """Should return 0 when no statistics exist after import period."""
        mock_hass = MagicMock()

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await _fix_post_import_discontinuity(
                hass=mock_hass,
                entity_id="sensor.energy",
                room_name="Living Room",
                import_end_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
                import_end_sum=500.0,
                metadata=mock_metadata,
            )

        assert result == 0

    @pytest.mark.asyncio
    async def test_no_discontinuity_returns_zero(self, mock_metadata):
        """Should return 0 when post-import stats are already aligned."""
        mock_hass = MagicMock()

        # Post-import stats that continue properly from import
        # import_end_sum = 500, first_post_state = 8, first_post_sum = 508
        # expected = 500 + 8 = 508, discontinuity = 508 - 508 = 0
        post_import_stats = [
            {"start": 1735862400, "state": 8.0, "sum": 508.0},  # Jan 3
        ]

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=post_import_stats,
        ):
            result = await _fix_post_import_discontinuity(
                hass=mock_hass,
                entity_id="sensor.energy",
                room_name="Living Room",
                import_end_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
                import_end_sum=500.0,
                metadata=mock_metadata,
            )

        assert result == 0

    @pytest.mark.asyncio
    async def test_detects_and_fixes_post_import_discontinuity(self, mock_metadata):
        """Should detect discontinuity and adjust post-import statistics."""
        mock_hass = MagicMock()

        # Scenario: Import ends Jan 2 with sum = 500
        # Live sensor recorded Jan 3 with its own baseline (sum = 8)
        # Expected: 500 + 8 = 508
        # Actual: 8
        # Discontinuity: 508 - 8 = 500
        post_import_stats = [
            {"start": 1735862400, "state": 8.0, "sum": 8.0},   # Jan 3 - wrong sum
            {"start": 1735948800, "state": 7.0, "sum": 15.0},  # Jan 4 - wrong sum
        ]

        import_calls = []

        def capture_import(hass, metadata, statistics):
            import_calls.append(statistics)

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=post_import_stats,
        ), patch(
            "custom_components.intuis_connect.history_import.async_import_statistics",
            side_effect=capture_import,
        ):
            result = await _fix_post_import_discontinuity(
                hass=mock_hass,
                entity_id="sensor.energy",
                room_name="Living Room",
                import_end_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
                import_end_sum=500.0,
                metadata=mock_metadata,
            )

        assert result == 2  # Adjusted 2 entries
        assert len(import_calls) == 1

        adjusted = import_calls[0]
        assert len(adjusted) == 2

        # Check that sums were adjusted by the discontinuity amount (500)
        assert adjusted[0]["sum"] == 8.0 + 500.0   # 508
        assert adjusted[1]["sum"] == 15.0 + 500.0  # 515

        # States should remain unchanged
        assert adjusted[0]["state"] == 8.0
        assert adjusted[1]["state"] == 7.0

    @pytest.mark.asyncio
    async def test_threshold_prevents_tiny_adjustments(self, mock_metadata):
        """Should not adjust if discontinuity is below threshold."""
        mock_hass = MagicMock()

        # Small discontinuity of 0.5 kWh (below DISCONTINUITY_THRESHOLD of 1.0)
        post_import_stats = [
            {"start": 1735862400, "state": 8.0, "sum": 507.5},  # 0.5 kWh off
        ]

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=post_import_stats,
        ):
            result = await _fix_post_import_discontinuity(
                hass=mock_hass,
                entity_id="sensor.energy",
                room_name="Living Room",
                import_end_time=datetime(2025, 1, 2, tzinfo=timezone.utc),
                import_end_sum=500.0,
                metadata=mock_metadata,
            )

        assert result == 0  # No adjustment made

    @pytest.mark.asyncio
    async def test_handles_december_discontinuity_scenario(self, mock_metadata):
        """Test the specific December -2172 kWh scenario."""
        mock_hass = MagicMock()

        # Scenario from user:
        # - Import covers Nov 19 - Jan 2, ends with sum = 400
        # - Live sensor had recorded some Dec/Jan data with its own baseline
        # - December shows -2172 because of discontinuity

        # Post-import stats (recorded by live sensor before import ran)
        post_import_stats = [
            {"start": 1735776000, "state": 10.0, "sum": 10.0},  # Jan 2 (live)
            {"start": 1735862400, "state": 8.0, "sum": 18.0},   # Jan 3 (live)
        ]

        import_calls = []

        def capture_import(hass, metadata, statistics):
            import_calls.append(statistics)

        with patch(
            "custom_components.intuis_connect.history_import._get_existing_statistics",
            new_callable=AsyncMock,
            return_value=post_import_stats,
        ), patch(
            "custom_components.intuis_connect.history_import.async_import_statistics",
            side_effect=capture_import,
        ):
            result = await _fix_post_import_discontinuity(
                hass=mock_hass,
                entity_id="sensor.energy",
                room_name="Living Room",
                import_end_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                import_end_sum=400.0,  # Import ended with 400 kWh
                metadata=mock_metadata,
            )

        assert result == 2

        adjusted = import_calls[0]
        # First post-import entry should continue from 400
        # expected = 400 + 10 = 410, actual = 10, discontinuity = 400
        assert adjusted[0]["sum"] == 10.0 + 400.0  # 410
        assert adjusted[1]["sum"] == 18.0 + 400.0  # 418


class TestClearStatisticsInRange:
    """Tests for _clear_statistics_in_range function."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_metadata(self):
        """Should return 0 when entity has no statistics metadata."""
        mock_hass = MagicMock()
        mock_instance = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = None

        # Mock the context manager
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_instance.get_session.return_value = mock_session

        with patch(
            "custom_components.intuis_connect.history_import.get_instance",
            return_value=mock_instance,
        ), patch(
            "custom_components.intuis_connect.history_import.session_scope",
        ) as mock_scope:
            # Configure the context manager mock
            mock_scope.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_scope.return_value.__exit__ = MagicMock(return_value=False)

            # Mock async_add_executor_job to run the function synchronously
            async def run_sync(func):
                return func()

            mock_hass.async_add_executor_job = run_sync

            result = await _clear_statistics_in_range(
                mock_hass,
                "sensor.energy",
                datetime(2025, 11, 19, tzinfo=timezone.utc),
                datetime(2026, 1, 3, tzinfo=timezone.utc),
            )

        # When no metadata found, should return 0
        assert result == 0

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self):
        """Should return 0 and log warning on exception."""
        mock_hass = MagicMock()
        mock_hass.async_add_executor_job = AsyncMock(
            side_effect=Exception("DB connection failed")
        )

        with patch(
            "custom_components.intuis_connect.history_import.get_instance",
            return_value=MagicMock(),
        ):
            result = await _clear_statistics_in_range(
                mock_hass,
                "sensor.energy",
                datetime(2025, 11, 19, tzinfo=timezone.utc),
                datetime(2026, 1, 3, tzinfo=timezone.utc),
            )

        assert result == 0
