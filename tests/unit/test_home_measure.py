"""One gethomemeasure request in place of one getroommeasure per room.

A home with eleven rooms was issuing eleven requests per hourly cycle and
being rate limited by the cloud; the home endpoint answers them all at once.
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.intuis_connect.intuis_api.api import APIError, IntuisAPI

HOUR = 3600
H0 = 1763337600  # an exact hour, UTC


def answer(rooms: list[dict[str, Any]]) -> dict[str, Any]:
    return {"body": {"home": {"id": "home1", "rooms": rooms}}}


def block(values: list[list[Any]], *, begin: int = H0 + 1800, step: int = HOUR) -> dict:
    """The cloud stamps a slot inside itself, at its middle for an hour."""
    return {"beg_time": begin, "step_time": step, "value": values}


def test_every_room_comes_back_from_one_answer() -> None:
    parsed = IntuisAPI._parse_home_measure(
        answer(
            [
                {"id": "r1", "measures": [block([[1200], [800]])]},
                {"id": "r2", "measures": [block([[50]])]},
            ]
        ),
        step=HOUR,
    )
    assert sorted(parsed) == ["r1", "r2"]
    assert parsed["r1"] == [(H0 + 1800, 1200.0), (H0 + 1800 + HOUR, 800.0)]


def test_a_measured_zero_is_kept_and_a_null_is_a_gap() -> None:
    parsed = IntuisAPI._parse_home_measure(
        answer([{"id": "r1", "measures": [block([[0], [None], [800]])]}]), step=HOUR
    )
    assert parsed["r1"] == [(H0 + 1800, 0.0), (H0 + 1800 + 2 * HOUR, 800.0)]


def test_tariff_columns_of_one_slot_are_summed() -> None:
    parsed = IntuisAPI._parse_home_measure(
        answer([{"id": "r1", "measures": [block([[100, None, 50]])]}]), step=HOUR
    )
    assert parsed["r1"] == [(H0 + 1800, 150.0)]


@pytest.mark.parametrize(
    "rooms",
    [
        [{"id": "r1", "measures": []}],
        [{"id": "r1", "measures": [block([[None], [None]])]}],
    ],
)
def test_a_room_without_measurement_stays_absent(rooms: list[dict]) -> None:
    """Absent, never a fabricated zero: the caller keeps treating it as a gap."""
    assert IntuisAPI._parse_home_measure(answer(rooms), step=HOUR) == {}


@pytest.mark.parametrize("value", [-5, float("nan"), True, "12"])
def test_an_invalid_measurement_is_refused(value: Any) -> None:
    with pytest.raises(APIError):
        IntuisAPI._parse_home_measure(
            answer([{"id": "r1", "measures": [block([[value]])]}]), step=HOUR
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"error": {"code": 1}},
        {"body": {}},
        {"body": {"home": {}}},
        {"body": {"home": {"rooms": "nope"}}},
        [],
    ],
)
def test_a_malformed_answer_is_refused(payload: Any) -> None:
    with pytest.raises(APIError):
        IntuisAPI._parse_home_measure(payload, step=HOUR)


def test_a_room_without_a_usable_id_is_refused() -> None:
    with pytest.raises(APIError):
        IntuisAPI._parse_home_measure(
            answer([{"measures": [block([[1]])]}]), step=HOUR
        )


def test_a_block_whose_step_differs_is_refused() -> None:
    """A step other than the requested scale would misplace every slot."""
    with pytest.raises(APIError):
        IntuisAPI._parse_home_measure(
            answer([{"id": "r1", "measures": [block([[1]], step=1800)]}]), step=HOUR
        )


class _Room:
    def __init__(self, bridge_id: str = "", modules: list | None = None) -> None:
        self.bridge_id = bridge_id
        self.modules = modules or []


class _Module:
    def __init__(self, bridge: str = "") -> None:
        self.bridge = bridge


class _Home:
    def __init__(self, rooms: dict | None = None) -> None:
        self.rooms = rooms if rooms is not None else {}


GATEWAY = "70:ee:50:44:26:13"
ROOMS = [("r1", "Entrée"), ("r2", "Salon")]
ENTRY = "entry1"


class _Hass:
    """Only the coordinator lookup bridged_rooms performs."""

    def __init__(self, modules: list | None = None) -> None:
        coordinator = type("C", (), {"data": {"modules": modules or []}})()
        self.data = {"intuis_connect": {ENTRY: {"coordinator": coordinator}}}


def test_a_room_without_a_bridge_borrows_the_home_gateway() -> None:
    """A home reports through one gateway, which the flow sends for every room."""
    from custom_components.intuis_connect.hourly_stats import bridged_rooms

    home = _Home(
        {
            "r1": _Room(modules=[_Module(), _Module(GATEWAY)]),
            "r2": _Room(),
        }
    )
    assert bridged_rooms(_Hass(), ENTRY, home, ROOMS) == [
        ("r1", GATEWAY),
        ("r2", GATEWAY),
    ]


def test_the_gateway_is_read_from_the_refreshed_coordinator_modules() -> None:
    """The home object built at setup carries no bridge; the modules do."""
    from custom_components.intuis_connect.hourly_stats import bridged_rooms

    hass = _Hass(modules=[_Module(), _Module(GATEWAY)])
    assert bridged_rooms(hass, ENTRY, _Home({"r1": _Room(), "r2": _Room()}), ROOMS) == [
        ("r1", GATEWAY),
        ("r2", GATEWAY),
    ]


def test_a_bridge_known_on_one_room_serves_the_others() -> None:
    from custom_components.intuis_connect.hourly_stats import bridged_rooms

    home = _Home({"r1": _Room(bridge_id=GATEWAY), "r2": _Room()})
    assert bridged_rooms(_Hass(), ENTRY, home, ROOMS) == [
        ("r1", GATEWAY),
        ("r2", GATEWAY),
    ]


def test_no_gateway_anywhere_means_no_bulk_request() -> None:
    """The endpoint answers 404 to a blank bridge; asking would only cost one."""
    from custom_components.intuis_connect.hourly_stats import bridged_rooms

    assert bridged_rooms(_Hass(), ENTRY, _Home({"r1": _Room()}), ROOMS) == []
    assert bridged_rooms(_Hass(), ENTRY, _Home(), ROOMS) == []
