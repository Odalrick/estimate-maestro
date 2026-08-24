from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from estimate_maestro.calibration import effort_detail, effort_table, summary
from estimate_maestro.config import load_config
from estimate_maestro.models import Estimate
from estimate_maestro.recording import Recorder
from estimate_maestro.store import Store

FROZEN = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)


@pytest.fixture
def prepared(tmp_path: Path) -> tuple[Store, object]:
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
    return store, config


def test_the_table_has_one_row_per_effort(prepared):
    store, config = prepared

    rows = effort_table(store, config)

    assert len(rows) == 1
    assert rows[0].effort == "2026-08-24-thing"
    assert rows[0].title == "Thing"


def test_the_row_carries_the_initial_triple_and_slice_count(prepared):
    store, config = prepared

    row = effort_table(store, config)[0]

    assert row.initial is not None
    assert row.initial.likely == 5
    assert row.slice_count_initial == 3
    assert row.final is None


def test_clocked_time_appears_as_wall_hours(prepared):
    store, config = prepared

    assert effort_table(store, config)[0].wall_hours == pytest.approx(2.0)


def test_fully_clocked_time_has_a_zero_derived_share(prepared):
    store, config = prepared

    assert effort_table(store, config)[0].derived_share == pytest.approx(0.0)


def test_effort_detail_returns_the_raw_logs(prepared):
    store, config = prepared

    detail = effort_detail(store, config, "2026-08-24-thing")

    assert detail.meta["title"] == "Thing"
    assert len(detail.estimates) == 1
    assert len(detail.slices) == 3
    assert len(detail.intervals) == 2
    assert detail.row.effort == "2026-08-24-thing"


def test_summary_refuses_to_pretend_below_the_minimum(prepared):
    store, config = prepared

    reported = summary(store, config)

    assert reported.efforts_counted == 1
    assert reported.median_hours_per_point is None
    assert "5" in reported.note
