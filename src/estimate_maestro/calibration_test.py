from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from estimate_maestro.calibration import effort_detail, effort_table, summary
from estimate_maestro.config import Config, load_config
from estimate_maestro.errors import UnknownEffort
from estimate_maestro.models import CommitEvent, Estimate
from estimate_maestro.recording import Recorder
from estimate_maestro.store import COMMITS_LOG, SLICES_LOG, Store

FROZEN = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)


def _recorder(store: Store, config: Config, moments: list[datetime]) -> Recorder:
    counter = iter(range(1, 1000))
    stream = iter(moments)
    return Recorder(
        store=store,
        config=config,
        now=lambda: next(stream),
        make_identifier=lambda prefix: f"{prefix}-{next(counter):04d}",
    )


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


def test_a_harvested_only_slice_gets_its_time_derived_from_commits(tmp_path: Path):
    store = Store(tmp_path / "store")
    store.initialise()
    config = load_config({"ESTIMATE_MAESTRO_STORE": str(tmp_path / "store")})
    recorder = _recorder(store, config, [FROZEN] * 20)
    plan = tmp_path / ".PR.md"
    plan.write_text("# plan\n")
    effort = recorder.start_effort(
        title="Solo Slice",
        kind="mega-pull-request",
        plan_path=plan,
        summary="A thing.",
        estimate=Estimate(optimistic=3, likely=5, pessimistic=9),
        rationale="Feels like a five.",
        work_slices=["Only"],
    ).identifier
    work_slice = store.read(effort, SLICES_LOG)[0]["slice"]
    store.append(
        effort,
        COMMITS_LOG,
        {
            "event": CommitEvent.HARVESTED,
            "slice": work_slice,
            "authored_at": datetime(2026, 8, 24, 10, 0, tzinfo=UTC).isoformat(),
        },
    )

    row = effort_table(store, config)[0]

    # A single commit at 10:00 derives a session from lead-in (09:30) to the
    # commit itself: 30 minutes, entirely inside working hours, no lunch overlap.
    assert row.wall_hours == pytest.approx(0.5)
    assert row.derived_share == pytest.approx(1.0)


def test_a_slice_with_a_closed_interval_ignores_its_harvested_commits(tmp_path: Path):
    store = Store(tmp_path / "store")
    store.initialise()
    config = load_config({"ESTIMATE_MAESTRO_STORE": str(tmp_path / "store")})
    recorder = _recorder(store, config, [FROZEN] * 20)
    plan = tmp_path / ".PR.md"
    plan.write_text("# plan\n")
    effort = recorder.start_effort(
        title="Paired Slice",
        kind="mega-pull-request",
        plan_path=plan,
        summary="A thing.",
        estimate=Estimate(optimistic=3, likely=5, pessimistic=9),
        rationale="Feels like a five.",
        work_slices=["Only"],
    ).identifier
    work_slice = store.read(effort, SLICES_LOG)[0]["slice"]
    recorder.clock_in(effort, work_slice=work_slice)
    recorder.clock_out(at=FROZEN + timedelta(hours=1))
    store.append(
        effort,
        COMMITS_LOG,
        {
            "event": CommitEvent.HARVESTED,
            "slice": work_slice,
            "authored_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC).isoformat(),
        },
    )

    row = effort_table(store, config)[0]

    # Recorded time wins: the one hour of clocked time stands, and the harvested
    # commit on the same (now-clocked) slice contributes nothing extra.
    assert row.wall_hours == pytest.approx(1.0)
    assert row.derived_share == pytest.approx(0.0)


def test_a_slice_with_an_open_interval_does_not_get_derived_time_added(tmp_path: Path):
    store = Store(tmp_path / "store")
    store.initialise()
    config = load_config({"ESTIMATE_MAESTRO_STORE": str(tmp_path / "store")})
    recorder = _recorder(store, config, [FROZEN] * 20)
    plan = tmp_path / ".PR.md"
    plan.write_text("# plan\n")
    effort = recorder.start_effort(
        title="In Flight Slice",
        kind="mega-pull-request",
        plan_path=plan,
        summary="A thing.",
        estimate=Estimate(optimistic=3, likely=5, pessimistic=9),
        rationale="Feels like a five.",
        work_slices=["Only"],
    ).identifier
    work_slice = store.read(effort, SLICES_LOG)[0]["slice"]
    recorder.clock_in(effort, work_slice=work_slice)  # never clocked out
    store.append(
        effort,
        COMMITS_LOG,
        {
            "event": CommitEvent.HARVESTED,
            "slice": work_slice,
            "authored_at": datetime(2026, 8, 24, 10, 0, tzinfo=UTC).isoformat(),
        },
    )

    row = effort_table(store, config)[0]

    # The slice is actively being worked (open interval): its harvested commit
    # must not be reconstructed into a phantom 0.5h session on top of the timer.
    assert row.wall_hours == pytest.approx(0.0)
    assert row.derived_share == pytest.approx(0.0)


def test_summary_reports_exact_medians_once_the_minimum_is_met(tmp_path: Path):
    store = Store(tmp_path / "store")
    store.initialise()
    config = load_config(
        {
            "ESTIMATE_MAESTRO_STORE": str(tmp_path / "store"),
            "ESTIMATE_MAESTRO_MINIMUM_EFFORTS": "3",
        }
    )
    recorder = _recorder(store, config, [FROZEN] * 40)
    plan = tmp_path / ".PR.md"
    plan.write_text("# plan\n")

    # (title, initial estimate, final estimate, clocked hours)
    # Effort One:   initial expected 4.0, final expected 4.0, 4.0h clocked
    #               -> hours/point 1.0, growth 1.0
    # Effort Two:   initial expected 2.0, final expected 3.0, 6.0h clocked
    #               -> hours/point 2.0, growth 1.5
    # Effort Three: initial expected 3.0, final expected 3.0, 1.5h clocked
    #               -> hours/point 0.5, growth 1.0
    specification = [
        (
            "Effort One",
            Estimate(optimistic=2, likely=4, pessimistic=6),
            Estimate(optimistic=4, likely=4, pessimistic=4),
            4.0,
        ),
        (
            "Effort Two",
            Estimate(optimistic=1, likely=2, pessimistic=3),
            Estimate(optimistic=2, likely=3, pessimistic=4),
            6.0,
        ),
        (
            "Effort Three",
            Estimate(optimistic=2, likely=3, pessimistic=4),
            Estimate(optimistic=3, likely=3, pessimistic=3),
            1.5,
        ),
    ]
    for title, initial, final, clocked_hours in specification:
        effort = recorder.start_effort(
            title=title,
            kind="mega-pull-request",
            plan_path=plan,
            summary="A thing.",
            estimate=initial,
            rationale="Sized.",
            work_slices=["Solo"],
        ).identifier
        recorder.clock_in(effort)
        recorder.clock_out(at=FROZEN + timedelta(hours=clocked_hours))
        recorder.record_final_plan(
            effort, plan_path=plan, summary="Wrapped.", estimate=final, rationale="Landed."
        )

    reported = summary(store, config)

    # sizing = [1.0, 2.0, 0.5] -> median 1.0, mean 3.5/3
    # growth  = [1.0, 1.5, 1.0] -> median 1.0, mean 3.5/3
    assert reported.efforts_counted == 3
    assert reported.median_hours_per_point == pytest.approx(1.0)
    assert reported.mean_hours_per_point == pytest.approx(3.5 / 3)
    assert reported.median_inventory_growth == pytest.approx(1.0)
    assert reported.mean_inventory_growth == pytest.approx(3.5 / 3)
    assert reported.note == "Based on 3 efforts, 3 of which have a final estimate."


def test_effort_detail_raises_a_named_error_for_an_unknown_effort(tmp_path: Path):
    store = Store(tmp_path / "store")
    store.initialise()
    config = load_config({"ESTIMATE_MAESTRO_STORE": str(tmp_path / "store")})

    with pytest.raises(UnknownEffort) as raised:
        effort_detail(store, config, "2026-01-01-does-not-exist")

    assert "unknown effort" in str(raised.value)
    assert "2026-01-01-does-not-exist" in str(raised.value)
