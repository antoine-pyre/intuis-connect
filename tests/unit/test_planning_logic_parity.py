"""The editor previews exactly the timetable rules the services apply.

Random cases run through timetable.py and the bundled planning-core.js (Node).
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.intuis_connect.entity.intuis_home_entity import (
    IntuisScheduleSummarySensor,
)
from custom_components.intuis_connect.entity.intuis_schedule import IntuisSchedule
from custom_components.intuis_connect.timetable import (
    replace_timetable_interval,
    schedule_slot_offsets,
)

CORE = (
    Path(__file__).parents[2]
    / "custom_components/intuis_connect/resources/planning/planning-core.js"
)
NODE = shutil.which("node")
SCRIPT = """
const core = require(process.argv[1]);
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const attempt = (fn) => { try { return fn(); } catch (error) { return null; } };
process.stdout.write(JSON.stringify(cases.map((c) => attempt(() => {
  const [start, end] = core.slotOffsets(c.start_day, c.start_time, c.end_day, c.end_time);
  return [start, end, core.replaceInterval(c.timetable, start, end, c.zone)];
}))));
"""


def python_result(case):
    try:
        start, end = schedule_slot_offsets(
            case["start_day"], case["start_time"], case["end_day"], case["end_time"]
        )
        return [start, end, replace_timetable_interval(case["timetable"], start, end, case["zone"])]
    except ValueError:
        return None


def random_case(rng):
    offsets = rng.sample(range(0, 10080, 30), rng.randint(1, 12))

    def clock():
        hours = rng.choice([0, 0, rng.randint(0, 23)])
        return f"{hours:02d}:{rng.choice([0, 30, rng.randint(0, 59)]):02d}"

    return {
        "timetable": [{"m_offset": o, "zone_id": rng.randint(0, 3)} for o in offsets],
        "start_day": str(rng.randint(0, 6)),
        "end_day": str(rng.randint(0, 6)),
        "start_time": clock(),
        "end_time": clock(),
        "zone": rng.randint(0, 3),
    }


@pytest.mark.skipif(NODE is None, reason="Node.js is required for the editor logic")
def test_editor_slot_and_interval_rules_match_services():
    rng = random.Random(20261027)
    cases = [random_case(rng) for _ in range(3000)]
    cases += [
        {**random_case(rng), "start_day": "6", "end_day": "6", "start_time": "22:00", "end_time": "00:00"},
        {**random_case(rng), "start_day": "4", "end_day": "0", "start_time": "22:00", "end_time": "06:00"},
        {**random_case(rng), "start_day": "0", "end_day": "0", "start_time": "10:00", "end_time": "10:00"},
    ]
    completed = subprocess.run(
        [NODE, "-e", SCRIPT, str(CORE)],
        input=json.dumps(cases), capture_output=True, text=True, check=True, timeout=60,
    )
    editor = json.loads(completed.stdout)
    for case, result in zip(cases, editor, strict=True):
        expected = python_result(case)
        if expected is not None:
            expected[2] = sorted(expected[2], key=lambda row: row["m_offset"])
        assert result == expected, case
    assert sum(result is None for result in editor) > 0
    assert sum(result is not None for result in editor) > 1000


@pytest.mark.skipif(NODE is None, reason="Node.js is required for the editor logic")
def test_editor_reads_the_actual_schedule_summary_attributes():
    schedule = IntuisSchedule.from_dict({
        "id": "sched-1", "name": "Semaine", "type": "therm", "selected": True,
        "away_temp": 16, "hg_temp": 7.5,
        "timetable": [{"m_offset": 0, "zone_id": 1}, {"m_offset": 420, "zone_id": 2}],
        "zones": [
            {"id": 1, "name": "<b>Nuit</b>", "type": 1,
             "rooms_temp": [{"room_id": "r1", "temp": 17.5}]},
            {"id": 2, "name": "Confort", "type": 0,
             "rooms_temp": [{"room_id": "r1", "temp": 20}]},
        ],
    })
    home = SimpleNamespace(
        id="home-1", name="Maison", schedules=[schedule],
        rooms={"r1": SimpleNamespace(name="Salon")},
    )
    sensor = IntuisScheduleSummarySensor(
        SimpleNamespace(data={"intuis_home": home}), "home-1", schedule
    )
    states = {"sensor.semaine": {
        "state": sensor.native_value, "attributes": sensor.extra_state_attributes,
    }}
    script = (
        "const core = require(process.argv[1]);"
        "const states = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        "process.stdout.write(JSON.stringify(core.parseHomes(states)));"
    )
    completed = subprocess.run(
        [NODE, "-e", script, str(CORE)], input=json.dumps(states),
        capture_output=True, text=True, check=True, timeout=60,
    )
    assert json.loads(completed.stdout) == [{
        "id": "home-1", "name": "Maison", "rooms": {"r1": "Salon"},
        "schedules": [{
            "entityId": "sensor.semaine", "id": "sched-1", "name": "Semaine", "active": True,
            "model": {
                "timetable": [{"m_offset": 0, "zone_id": 1}, {"m_offset": 420, "zone_id": 2}],
                "awayTemp": 16, "hgTemp": 7.5,
                "zones": [
                    {"id": 1, "name": "<b>Nuit</b>", "type": 1, "temps": {"r1": 17.5}},
                    {"id": 2, "name": "Confort", "type": 0, "temps": {"r1": 20}},
                ],
            },
        }],
    }]
