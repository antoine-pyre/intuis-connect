"""Issue #38: a failing home config fetch must keep the last good config
instead of aborting the whole coordinator update."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from custom_components.intuis_connect.intuis_api.api import APIError


async def test_config_failure_keeps_last_good_config(
    intuis_data_factory, mock_api, sample_room_data
):
    """When async_get_config fails, async_update keeps the previous home config
    and still returns the room data, rather than raising (issue #38)."""
    data = intuis_data_factory()
    good = {"home_id": "home_123", "modules": [{"id": "gw_1"}]}
    mock_api.async_get_config = AsyncMock(side_effect=[good, APIError("boom")])

    with patch(
        "custom_components.intuis_connect.intuis_data.extract_rooms",
        return_value=sample_room_data,
    ), patch(
        "custom_components.intuis_connect.intuis_data.extract_modules",
        return_value=[],
    ):
        first = await data.async_update()
        second = await data.async_update()

    assert second["rooms"] == sample_room_data
    assert second["home_config"] is first["home_config"]
    assert second["home_config"].module_id == "gw_1"
