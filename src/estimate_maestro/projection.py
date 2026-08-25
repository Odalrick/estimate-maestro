from datetime import datetime
from typing import Any

from estimate_maestro.models import IntervalEvent, IntervalKind, Provenance, SliceEvent
from estimate_maestro.timesheet import MeasuredInterval


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


def clocked_slices(interval_records: list[dict[str, Any]]) -> set[str | None]:
    return {
        record.get("slice")
        for record in interval_records
        if record.get("event") == IntervalEvent.CLOCK_IN
    }


def closed_intervals(interval_records: list[dict[str, Any]]) -> set[str]:
    return {
        record["interval"]
        for record in interval_records
        if record.get("event") == IntervalEvent.CLOCK_OUT
    }


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


def measured_intervals(interval_records: list[dict[str, Any]]) -> list[MeasuredInterval]:
    started: dict[str, dict[str, Any]] = {}
    stopped: dict[str, dict[str, Any]] = {}
    repairs: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in interval_records:
        interval = record["interval"]
        event = record.get("event")
        if event == IntervalEvent.CLOCK_IN:
            started[interval] = record
            order.append(interval)
        elif event == IntervalEvent.CLOCK_OUT:
            stopped[interval] = record
        elif event == IntervalEvent.REPAIR:
            repairs[interval] = {**repairs.get(interval, {}), **record}

    measured: list[MeasuredInterval] = []
    for interval in order:
        if interval not in stopped:
            continue
        opened = started[interval]
        closed = stopped[interval]
        repair = repairs.get(interval, {})
        measured.append(
            MeasuredInterval(
                start=datetime.fromisoformat(repair.get("start", opened["at"])),
                stop=datetime.fromisoformat(repair.get("stop", closed["at"])),
                provenance=Provenance(repair.get("provenance", closed["provenance"])),
                work_slice=opened.get("slice"),
                kind=IntervalKind(opened.get("kind", IntervalKind.WORK)),
            )
        )
    return measured
