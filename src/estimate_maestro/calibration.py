from collections import defaultdict
from datetime import datetime
from statistics import fmean, median
from typing import Any

from pydantic import BaseModel

from estimate_maestro.config import Config
from estimate_maestro.errors import UnknownEffort
from estimate_maestro.models import CommitEvent, Estimate, EstimatePass, Provenance
from estimate_maestro.projection import clocked_slices, measured_intervals, slice_count
from estimate_maestro.store import COMMITS_LOG, ESTIMATES_LOG, INTERVALS_LOG, SLICES_LOG, Store
from estimate_maestro.timesheet import MeasuredInterval, derive_intervals, wall_seconds


class EffortRow(BaseModel):
    effort: str
    title: str
    kind: str
    status: str
    initial: Estimate | None
    final: Estimate | None
    wall_hours: float
    calendar_days: float
    slice_count_initial: int
    slice_count_final: int
    derived_share: float


class EffortDetail(BaseModel):
    meta: dict[str, Any]
    estimates: list[dict[str, Any]]
    slices: list[dict[str, Any]]
    intervals: list[dict[str, Any]]
    commits: list[dict[str, Any]]
    row: EffortRow


class Summary(BaseModel):
    efforts_counted: int
    mean_hours_per_point: float | None
    median_hours_per_point: float | None
    mean_inventory_growth: float | None
    median_inventory_growth: float | None
    note: str


def _estimate_for(records: list[dict[str, Any]], which: EstimatePass) -> Estimate | None:
    for record in reversed(records):
        if record["pass"] == which:
            return Estimate.model_validate(record["estimate"])
    return None


def _slice_count_at(records: list[dict[str, Any]], which: EstimatePass) -> int:
    for record in reversed(records):
        if record["pass"] == which:
            return int(record["slice_count"])
    return 0


def _intervals_for(store: Store, config: Config, effort: str) -> list[MeasuredInterval]:
    interval_records = store.read(effort, INTERVALS_LOG)
    measured = measured_intervals(interval_records)
    clocked = clocked_slices(interval_records)
    by_slice: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for record in store.read(effort, COMMITS_LOG):
        if record.get("event") == CommitEvent.HARVESTED:
            by_slice[record.get("slice")].append(record)
    derived: list[MeasuredInterval] = []
    for work_slice, records in by_slice.items():
        if work_slice in clocked:
            continue
        derived.extend(derive_intervals(records, config, work_slice))
    return measured + derived


def _calendar_days(store: Store, effort: str, intervals: list[MeasuredInterval]) -> float:
    moments = [datetime.fromisoformat(store.read_meta(effort)["created_at"])]
    moments.extend(interval.stop for interval in intervals)
    moments.extend(
        datetime.fromisoformat(record["at"]) for record in store.read(effort, ESTIMATES_LOG)
    )
    return (max(moments) - min(moments)).total_seconds() / 86400


def effort_table(store: Store, config: Config) -> list[EffortRow]:
    absences = store.read_absences()
    rows: list[EffortRow] = []
    for effort in store.list_efforts():
        meta = store.read_meta(effort)
        estimates = store.read(effort, ESTIMATES_LOG)
        intervals = _intervals_for(store, config, effort)
        total = wall_seconds(intervals, absences, config.working_hours)
        derived_only = [
            interval
            for interval in intervals
            if interval.provenance is Provenance.DERIVED_FROM_COMMITS
        ]
        derived_total = wall_seconds(derived_only, absences, config.working_hours)
        rows.append(
            EffortRow(
                effort=effort,
                title=meta["title"],
                kind=meta["kind"],
                status=meta["status"],
                initial=_estimate_for(estimates, EstimatePass.INITIAL),
                final=_estimate_for(estimates, EstimatePass.FINAL),
                wall_hours=total / 3600,
                calendar_days=_calendar_days(store, effort, intervals),
                slice_count_initial=_slice_count_at(estimates, EstimatePass.INITIAL),
                slice_count_final=slice_count(store.read(effort, SLICES_LOG)),
                derived_share=(derived_total / total) if total else 0.0,
            )
        )
    return rows


def effort_detail(store: Store, config: Config, effort: str) -> EffortDetail:
    if effort not in store.list_efforts():
        raise UnknownEffort(effort)
    return EffortDetail(
        meta=store.read_meta(effort),
        estimates=store.read(effort, ESTIMATES_LOG),
        slices=store.read(effort, SLICES_LOG),
        intervals=store.read(effort, INTERVALS_LOG),
        commits=store.read(effort, COMMITS_LOG),
        row=next(row for row in effort_table(store, config) if row.effort == effort),
    )


def summary(store: Store, config: Config) -> Summary:
    rows = effort_table(store, config)
    sizing = [
        row.wall_hours / row.final.expected
        for row in rows
        if row.final is not None and row.final.expected > 0 and row.wall_hours > 0
    ]
    growth = [
        row.final.expected / row.initial.expected
        for row in rows
        if row.initial is not None and row.final is not None and row.initial.expected > 0
    ]
    minimum = config.minimum_efforts_for_analysis
    if len(rows) < minimum:
        return Summary(
            efforts_counted=len(rows),
            mean_hours_per_point=None,
            median_hours_per_point=None,
            mean_inventory_growth=None,
            median_inventory_growth=None,
            note=(
                f"{len(rows)} effort(s) recorded; calibration is not established below "
                f"{minimum}. Read the table instead."
            ),
        )
    return Summary(
        efforts_counted=len(rows),
        mean_hours_per_point=fmean(sizing) if sizing else None,
        median_hours_per_point=median(sizing) if sizing else None,
        mean_inventory_growth=fmean(growth) if growth else None,
        median_inventory_growth=median(growth) if growth else None,
        note=f"Based on {len(rows)} efforts, {len(sizing)} of which have a final estimate.",
    )
