import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from estimate_maestro.config import load_config
from estimate_maestro.models import Estimate
from estimate_maestro.recording import Recorder
from estimate_maestro.responses import ToolCategory, tainted_field_names
from estimate_maestro.server import TOOL_CATEGORIES, TOOL_RESPONSES, build_server
from estimate_maestro.store import ESTIMATES_LOG, Store

FROZEN = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)


@pytest.fixture
def server(tmp_path: Path):
    store = Store(tmp_path / "store")
    store.initialise()
    return build_server(store, load_config({"ESTIMATE_MAESTRO_STORE": str(tmp_path / "store")}))


@pytest.fixture
def prepared(tmp_path: Path):
    """A server backed by a store seeded, via the real `Recorder`, with one finished
    two-hour effort of three slices under frozen time and deterministic identifiers —
    the fixture used to pin exact calibration and estimation output.
    """
    store = Store(tmp_path / "store")
    store.initialise()
    config = load_config({"ESTIMATE_MAESTRO_STORE": str(tmp_path / "store")})
    counter = iter(range(1, 1000))
    moments = iter([FROZEN] * 200)
    recorder = Recorder(
        store=store,
        config=config,
        now=lambda: next(moments),
        make_identifier=lambda prefix: f"{prefix}-{next(counter):04d}",
    )
    plan = tmp_path / ".PR.md"
    plan.write_text("# plan\n")
    effort = recorder.start_effort(
        title="Thing",
        kind="mega-pull-request",
        plan_path=plan,
        summary="A thing.",
        estimate=Estimate(optimistic=3, likely=5, pessimistic=9),
        rationale="Feels like a five.",
        work_slices=["One", "Two", "Three"],
    ).identifier
    recorder.clock_in(effort)
    recorder.clock_out(at=FROZEN + timedelta(hours=2))
    return build_server(store, config)


def registered_names(server) -> set[str]:
    return {tool.name for tool in asyncio.run(server.list_tools())}


def test_every_registered_tool_declares_a_category(server):
    assert registered_names(server) == set(TOOL_CATEGORIES)


def test_every_categorised_tool_declares_a_response_model():
    assert set(TOOL_CATEGORIES) == set(TOOL_RESPONSES)


def test_no_untainted_category_leaks_a_duration_or_aggregate():
    offenders = {
        name: tainted_field_names(TOOL_RESPONSES[name])
        for name, category in TOOL_CATEGORIES.items()
        if category is not ToolCategory.CALIBRATION
    }

    assert {name: found for name, found in offenders.items() if found} == {}


def test_the_recording_surface_answers_with_acknowledgements_only():
    from estimate_maestro.responses import Acknowledgement

    recording = [
        name for name, category in TOOL_CATEGORIES.items() if category is ToolCategory.RECORDING
    ]

    assert recording
    assert all(TOOL_RESPONSES[name] is Acknowledgement for name in recording)


def test_the_calibration_surface_is_the_only_one_permitted_aggregates():
    from estimate_maestro.calibration import Summary

    assert tainted_field_names(Summary) != []
    assert TOOL_CATEGORIES["summary"] is ToolCategory.CALIBRATION


def test_start_effort_dispatch_writes_a_genuine_effort_to_the_store(server, tmp_path: Path):
    plan = tmp_path / "plan.md"
    plan.write_text("# plan\n")

    result = asyncio.run(
        server.call_tool(
            "start_effort",
            {
                "title": "Widget Rework",
                "kind": "mega-pull-request",
                "plan_path": str(plan),
                "summary_text": "Rework the widget.",
                "optimistic": 2,
                "likely": 4,
                "pessimistic": 8,
                "rationale": "Looks like a four.",
                "work_slices": ["Design", "Build"],
            },
        )
    )

    assert result.is_error is False
    effort = result.structured_content["identifier"]
    assert result.structured_content == {"recorded": "effort", "identifier": effort}

    store = Store(tmp_path / "store")
    meta = store.read_meta(effort)
    assert meta["title"] == "Widget Rework"

    estimates = store.read(effort, ESTIMATES_LOG)
    assert len(estimates) == 1
    assert estimates[0]["estimate"] == {
        "scale": "points",
        "optimistic": 2.0,
        "likely": 4.0,
        "pessimistic": 8.0,
    }


def test_current_dispatch_reports_the_clocked_in_effort_and_slice(server, tmp_path: Path):
    plan = tmp_path / "plan.md"
    plan.write_text("# plan\n")

    start_result = asyncio.run(
        server.call_tool(
            "start_effort",
            {
                "title": "Widget Rework",
                "kind": "mega-pull-request",
                "plan_path": str(plan),
                "summary_text": "Rework the widget.",
                "optimistic": 2,
                "likely": 4,
                "pessimistic": 8,
                "rationale": "Looks like a four.",
                "work_slices": [],
            },
        )
    )
    effort = start_result.structured_content["identifier"]

    add_slice_result = asyncio.run(
        server.call_tool("add_slice", {"effort": effort, "title": "Design"})
    )
    work_slice = add_slice_result.structured_content["identifier"]

    before = datetime.now(UTC)
    clock_in_result = asyncio.run(
        server.call_tool("clock_in", {"effort": effort, "work_slice": work_slice})
    )
    after = datetime.now(UTC)
    interval = clock_in_result.structured_content["identifier"]

    reported = asyncio.run(server.call_tool("current", {})).structured_content

    assert reported["effort"] == effort
    assert reported["work_slice"] == work_slice
    assert reported["interval"] == interval
    assert before <= datetime.fromisoformat(reported["since"]) <= after


def test_effort_table_dispatch_returns_exact_row_values(prepared):
    rows = asyncio.run(prepared.call_tool("effort_table", {})).structured_content["result"]

    assert len(rows) == 1
    row = rows[0]
    assert row["calendar_days"] == pytest.approx(2 / 24)
    row_without_calendar_days = {key: value for key, value in row.items() if key != "calendar_days"}
    assert row_without_calendar_days == {
        "effort": "2026-08-24-thing",
        "title": "Thing",
        "kind": "mega-pull-request",
        "status": "active",
        "initial": {"scale": "points", "optimistic": 3.0, "likely": 5.0, "pessimistic": 9.0},
        "final": None,
        "wall_hours": 2.0,
        "slice_count_initial": 3,
        "slice_count_final": 3,
        "derived_share": 0.0,
    }


def test_reference_efforts_dispatch_returns_the_exact_list(prepared):
    result = asyncio.run(prepared.call_tool("reference_efforts", {}))

    assert result.structured_content == {
        "result": [
            {
                "effort": "2026-08-24-thing",
                "title": "Thing",
                "kind": "mega-pull-request",
                "summary": "A thing.",
                "initial": {
                    "scale": "points",
                    "optimistic": 3.0,
                    "likely": 5.0,
                    "pessimistic": 9.0,
                },
                "final": None,
            }
        ]
    }
