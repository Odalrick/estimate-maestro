from dataclasses import dataclass
from datetime import datetime
from typing import Any

from estimate_maestro.clock import overlap_seconds
from estimate_maestro.models import IntervalKind, Provenance


@dataclass(frozen=True)
class MeasuredInterval:
    start: datetime
    stop: datetime
    provenance: Provenance
    work_slice: str | None
    kind: IntervalKind


def _absent_seconds(measured: MeasuredInterval, absences: list[dict[str, Any]]) -> float:
    clipped: list[tuple[datetime, datetime]] = []
    for absence in absences:
        overlap = overlap_seconds(
            measured.start,
            measured.stop,
            datetime.fromisoformat(absence["start"]),
            datetime.fromisoformat(absence["stop"]),
        )
        if overlap <= 0.0:
            continue
        clipped_start = max(measured.start, datetime.fromisoformat(absence["start"]))
        clipped_stop = min(measured.stop, datetime.fromisoformat(absence["stop"]))
        clipped.append((clipped_start, clipped_stop))

    clipped.sort(key=lambda span: span[0])
    merged: list[tuple[datetime, datetime]] = []
    for start, stop in clipped:
        if merged and start <= merged[-1][1]:
            previous_start, previous_stop = merged[-1]
            merged[-1] = (previous_start, max(previous_stop, stop))
        else:
            merged.append((start, stop))

    return sum((stop - start).total_seconds() for start, stop in merged)


def wall_seconds(intervals: list[MeasuredInterval], absences: list[dict[str, Any]]) -> float:
    total = 0.0
    for measured in intervals:
        duration = max(0.0, (measured.stop - measured.start).total_seconds())
        absent = _absent_seconds(measured, absences)
        total += max(0.0, duration - absent)
    return total
