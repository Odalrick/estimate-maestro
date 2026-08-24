from typing import Any

from estimate_maestro.models import IntervalEvent, SliceEvent


def live_slices(slice_records: list[dict[str, Any]]) -> set[str]:
    live: set[str] = set()
    for record in slice_records:
        event = record.get("event")
        if event == SliceEvent.ADDED:
            live.add(record["slice"])
        elif event == SliceEvent.DROPPED:
            live.discard(record["slice"])
    return live


def slice_count(slice_records: list[dict[str, Any]]) -> int:
    return len(live_slices(slice_records))


def open_interval(interval_records: list[dict[str, Any]]) -> dict[str, Any] | None:
    opened: dict[str, dict[str, Any]] = {}
    for record in interval_records:
        event = record.get("event")
        if event == IntervalEvent.CLOCK_IN:
            opened[record["interval"]] = record
        elif event == IntervalEvent.CLOCK_OUT:
            opened.pop(record["interval"], None)
    if not opened:
        return None
    return list(opened.values())[-1]
