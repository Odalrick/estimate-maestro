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


def wall_seconds(intervals: list[MeasuredInterval], absences: list[dict[str, Any]]) -> float:
    total = 0.0
    for measured in intervals:
        total += max(0.0, (measured.stop - measured.start).total_seconds())
        for absence in absences:
            total -= overlap_seconds(
                measured.start,
                measured.stop,
                datetime.fromisoformat(absence["start"]),
                datetime.fromisoformat(absence["stop"]),
            )
    return max(0.0, total)
