from dataclasses import dataclass
from datetime import datetime
from typing import Any

from estimate_maestro.clock import overlap_seconds, working_seconds_between
from estimate_maestro.config import Config, WorkingHours
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


def derive_intervals(
    commit_records: list[dict[str, Any]], config: Config, work_slice: str | None
) -> list[MeasuredInterval]:
    moments = sorted(
        datetime.fromisoformat(record["authored_at"])
        for record in commit_records
        if "authored_at" in record
    )
    if not moments:
        return []
    gap_limit = config.derive_session_gap.total_seconds()
    sessions: list[tuple[datetime, datetime]] = []
    session_start = moments[0] - config.derive_lead_in
    previous = moments[0]
    for moment in moments[1:]:
        if working_seconds_between(previous, moment, config.working_hours) > gap_limit:
            sessions.append((session_start, previous))
            session_start = moment - config.derive_lead_in
        previous = moment
    sessions.append((session_start, previous))
    return [
        MeasuredInterval(
            start=start,
            stop=stop,
            provenance=Provenance.DERIVED_FROM_COMMITS,
            work_slice=work_slice,
            kind=IntervalKind.WORK,
        )
        for start, stop in sessions
    ]


def wall_seconds(
    intervals: list[MeasuredInterval], absences: list[dict[str, Any]], hours: WorkingHours
) -> float:
    total = 0.0
    for measured in intervals:
        if measured.provenance is Provenance.DERIVED_FROM_COMMITS:
            duration = working_seconds_between(measured.start, measured.stop, hours)
        else:
            duration = max(0.0, (measured.stop - measured.start).total_seconds())
        total += max(0.0, duration - _absent_seconds(measured, absences))
    return total
