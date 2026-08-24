from datetime import UTC, datetime

import pytest

from estimate_maestro.models import IntervalKind, Provenance
from estimate_maestro.projection import measured_intervals
from estimate_maestro.timesheet import MeasuredInterval, wall_seconds


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 24, hour, minute, tzinfo=UTC)


def interval(start: datetime, stop: datetime) -> MeasuredInterval:
    return MeasuredInterval(
        start=start,
        stop=stop,
        provenance=Provenance.MANUAL,
        work_slice=None,
        kind=IntervalKind.WORK,
    )


def test_wall_time_is_the_sum_of_interval_durations():
    intervals = [interval(at(9), at(11)), interval(at(13), at(14))]

    assert wall_seconds(intervals, absences=[]) == pytest.approx(3 * 3600)


def test_a_manual_interval_outside_working_hours_counts_in_full():
    saturday_evening = datetime(2026, 8, 29, 20, tzinfo=UTC)
    late = datetime(2026, 8, 29, 23, tzinfo=UTC)

    assert wall_seconds([interval(saturday_evening, late)], absences=[]) == pytest.approx(3 * 3600)


def test_an_absence_is_deducted_from_an_overlapping_interval():
    absences = [{"start": at(10).isoformat(), "stop": at(11).isoformat(), "kind": "appointment"}]

    assert wall_seconds([interval(at(9), at(12))], absences) == pytest.approx(2 * 3600)


def test_an_absence_that_does_not_overlap_deducts_nothing():
    absences = [{"start": at(15).isoformat(), "stop": at(16).isoformat(), "kind": "vacation"}]

    assert wall_seconds([interval(at(9), at(12))], absences) == pytest.approx(3 * 3600)


def test_a_repair_replaces_the_recorded_bounds():
    records = [
        {
            "event": "clock_in",
            "interval": "iv-01",
            "slice": None,
            "kind": "work",
            "at": at(9).isoformat(),
        },
        {
            "event": "clock_out",
            "interval": "iv-01",
            "provenance": "manual",
            "at": at(12).isoformat(),
        },
        {
            "event": "repair",
            "interval": "iv-01",
            "provenance": "repaired",
            "start": at(10, 30).isoformat(),
            "at": at(18).isoformat(),
        },
    ]

    measured = measured_intervals(records)

    assert len(measured) == 1
    assert measured[0].start == at(10, 30)
    assert measured[0].provenance is Provenance.REPAIRED


def test_a_still_open_interval_is_not_measured():
    records = [
        {
            "event": "clock_in",
            "interval": "iv-01",
            "slice": None,
            "kind": "work",
            "at": at(9).isoformat(),
        }
    ]

    assert measured_intervals(records) == []


def test_overlapping_absences_deduct_the_shared_region_only_once():
    absences = [
        {"start": at(10).isoformat(), "stop": at(11).isoformat(), "kind": "appointment"},
        {"start": at(10, 30).isoformat(), "stop": at(11, 30).isoformat(), "kind": "vacation"},
    ]

    assert wall_seconds([interval(at(9), at(12))], absences) == pytest.approx(1.5 * 3600)


def test_absences_exceeding_one_intervals_duration_do_not_leak_into_anothers_total():
    over_absent = interval(at(9), at(10))
    untouched = interval(at(14), at(15))
    absences = [
        {"start": at(9).isoformat(), "stop": at(10).isoformat(), "kind": "appointment"},
        {"start": at(9, 30).isoformat(), "stop": at(10, 30).isoformat(), "kind": "vacation"},
    ]

    assert wall_seconds([over_absent, untouched], absences) == pytest.approx(3600)


def test_two_repairs_merge_cumulatively():
    records = [
        {
            "event": "clock_in",
            "interval": "iv-01",
            "slice": None,
            "kind": "work",
            "at": at(9).isoformat(),
        },
        {
            "event": "clock_out",
            "interval": "iv-01",
            "provenance": "manual",
            "at": at(12).isoformat(),
        },
        {
            "event": "repair",
            "interval": "iv-01",
            "provenance": "repaired",
            "start": at(10, 30).isoformat(),
            "at": at(18).isoformat(),
        },
        {
            "event": "repair",
            "interval": "iv-01",
            "provenance": "repaired",
            "stop": at(11, 30).isoformat(),
            "at": at(19).isoformat(),
        },
    ]

    measured = measured_intervals(records)

    assert len(measured) == 1
    assert measured[0].start == at(10, 30)
    assert measured[0].stop == at(11, 30)


def test_a_repair_supplying_only_stop_falls_back_to_the_recorded_start():
    records = [
        {
            "event": "clock_in",
            "interval": "iv-01",
            "slice": None,
            "kind": "work",
            "at": at(9).isoformat(),
        },
        {
            "event": "clock_out",
            "interval": "iv-01",
            "provenance": "manual",
            "at": at(12).isoformat(),
        },
        {
            "event": "repair",
            "interval": "iv-01",
            "provenance": "repaired",
            "stop": at(11, 30).isoformat(),
            "at": at(18).isoformat(),
        },
    ]

    measured = measured_intervals(records)

    assert len(measured) == 1
    assert measured[0].start == at(9)
    assert measured[0].stop == at(11, 30)
