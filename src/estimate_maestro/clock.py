from datetime import date, datetime, time, timedelta

from estimate_maestro.config import Config, WorkingHours


def _combine(day: date, moment: time, reference: datetime) -> datetime:
    return datetime.combine(day, moment, tzinfo=reference.tzinfo)


def _span_seconds(start: datetime, stop: datetime) -> float:
    return max(0.0, (stop - start).total_seconds())


def working_seconds_between(start: datetime, stop: datetime, hours: WorkingHours) -> float:
    if stop <= start:
        return 0.0
    total = 0.0
    day = start.date()
    while day <= stop.date():
        if day.weekday() in hours.workdays:
            window_start = max(start, _combine(day, hours.day_start, start))
            window_stop = min(stop, _combine(day, hours.day_end, start))
            total += _span_seconds(window_start, window_stop)
            lunch_start = max(window_start, _combine(day, hours.lunch_start, start))
            lunch_stop = min(window_stop, _combine(day, hours.lunch_end, start))
            total -= _span_seconds(lunch_start, lunch_stop)
        day += timedelta(days=1)
    return total


def clamp_stop(start: datetime, last_activity: datetime, config: Config) -> datetime:
    hours = config.working_hours
    # Strict at the upper bound: `day_end` is where the working day stops, not a
    # moment inside it. Inclusive, a session begun at exactly 17:00 clamps to
    # 17:00 and records nothing at all, while one begun at 17:01 gets the
    # off-hours cap.
    within_model = (
        start.weekday() in hours.workdays
        and hours.day_start <= start.timetz().replace(tzinfo=None) < hours.day_end
    )
    if within_model:
        limit = _combine(start.date(), hours.day_end, start)
    else:
        limit = start + config.off_hours_session_cap
    return min(last_activity, limit)


def overlap_seconds(
    first_start: datetime, first_stop: datetime, second_start: datetime, second_stop: datetime
) -> float:
    return _span_seconds(max(first_start, second_start), min(first_stop, second_stop))
