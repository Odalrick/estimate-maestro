from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from estimate_maestro.clock import clamp_stop, overlap_seconds, working_seconds_between
from estimate_maestro.config import load_config

STOCKHOLM = ZoneInfo("Europe/Stockholm")
HOURS = load_config({}).working_hours


def at(day: int, hour: int, minute: int = 0) -> datetime:
    # August 2026: the 24th is a Monday, so day 28 is Friday and 29 a Saturday.
    return datetime(2026, 8, day, hour, minute, tzinfo=STOCKHOLM)


def test_a_morning_inside_working_hours_counts_in_full():
    assert working_seconds_between(at(24, 9), at(24, 12), HOURS) == pytest.approx(3 * 3600)


def test_a_full_day_has_lunch_deducted():
    assert working_seconds_between(at(24, 9), at(24, 17), HOURS) == pytest.approx(7 * 3600)


def test_a_span_straddling_lunch_counts_only_the_working_halves():
    assert working_seconds_between(at(24, 11, 30), at(24, 13, 30), HOURS) == pytest.approx(3600)


def test_time_outside_the_working_day_does_not_count():
    assert working_seconds_between(at(24, 18), at(24, 20), HOURS) == pytest.approx(0)


def test_a_weekend_does_not_count():
    assert working_seconds_between(at(29, 9), at(30, 17), HOURS) == pytest.approx(0)


def test_a_span_across_a_weekend_counts_only_the_workdays():
    # Friday 15:00 to Monday 10:00 = 2h Friday + 1h Monday.
    assert working_seconds_between(at(28, 15), at(31, 10), HOURS) == pytest.approx(3 * 3600)


def test_a_reversed_span_is_zero_rather_than_negative():
    assert working_seconds_between(at(24, 17), at(24, 9), HOURS) == pytest.approx(0)


def test_a_timer_left_running_clamps_to_the_end_of_its_own_workday():
    config = load_config({})

    assert clamp_stop(at(28, 15), last_activity=at(31, 9, 30), config=config) == at(28, 17)


def test_clamping_prefers_the_last_activity_when_it_comes_first():
    config = load_config({})

    assert clamp_stop(at(24, 9), last_activity=at(24, 11), config=config) == at(24, 11)


def test_a_start_outside_the_model_clamps_to_the_off_hours_cap():
    config = load_config({})

    assert clamp_stop(at(29, 20), last_activity=at(30, 9), config=config) == at(29, 20) + timedelta(
        hours=4
    )


def test_a_start_at_exactly_the_end_of_the_day_takes_the_off_hours_cap():
    config = load_config({})

    # 17:00 is the boundary, not a working moment: treated as inside the model it
    # clamps to 17:00 and records a session of exactly nothing, while 17:01 gets
    # the four-hour cap.
    assert clamp_stop(at(24, 17), last_activity=at(25, 9), config=config) == at(24, 17) + timedelta(
        hours=4
    )


def test_a_start_at_exactly_the_start_of_the_day_is_inside_the_model():
    config = load_config({})

    assert clamp_stop(at(24, 9), last_activity=at(25, 9), config=config) == at(24, 17)


def test_overlap_is_zero_when_two_spans_do_not_touch():
    assert overlap_seconds(at(24, 9), at(24, 10), at(24, 11), at(24, 12)) == pytest.approx(0)


def test_overlap_is_the_intersection_when_two_spans_cross():
    assert overlap_seconds(at(24, 9), at(24, 12), at(24, 11), at(24, 14)) == pytest.approx(3600)
