from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time, timedelta
from pathlib import Path

DEFAULT_STORE_PATH = "~/mcp/estimate-maestro-store"


@dataclass(frozen=True)
class WorkingHours:
    day_start: time
    day_end: time
    lunch_start: time
    lunch_end: time
    workdays: frozenset[int]


@dataclass(frozen=True)
class Config:
    store_path: Path
    working_hours: WorkingHours
    off_hours_session_cap: timedelta
    derive_lead_in: timedelta
    derive_session_gap: timedelta
    minimum_efforts_for_analysis: int


def _read_time(environment: Mapping[str, str], name: str, fallback: time) -> time:
    raw = environment.get(name)
    if raw is None:
        return fallback
    try:
        return time.fromisoformat(raw)
    except ValueError as error:
        raise ValueError(f"{name} is not an ISO 8601 time: {raw!r}") from error


def _read_minutes(environment: Mapping[str, str], name: str, fallback: timedelta) -> timedelta:
    raw = environment.get(name)
    if raw is None:
        return fallback
    try:
        return timedelta(minutes=int(raw))
    except ValueError as error:
        raise ValueError(f"{name} is not a whole number of minutes: {raw!r}") from error


def _read_workdays(
    environment: Mapping[str, str], name: str, fallback: frozenset[int]
) -> frozenset[int]:
    raw = environment.get(name)
    if raw is None:
        return fallback
    try:
        return frozenset(int(part) for part in raw.split(","))
    except ValueError as error:
        raise ValueError(f"{name} is not a comma-separated list of weekdays: {raw!r}") from error


def load_config(environment: Mapping[str, str]) -> Config:
    working_hours = WorkingHours(
        day_start=_read_time(environment, "ESTIMATE_MAESTRO_DAY_START", time(9, 0)),
        day_end=_read_time(environment, "ESTIMATE_MAESTRO_DAY_END", time(17, 0)),
        lunch_start=_read_time(environment, "ESTIMATE_MAESTRO_LUNCH_START", time(12, 0)),
        lunch_end=_read_time(environment, "ESTIMATE_MAESTRO_LUNCH_END", time(13, 0)),
        workdays=_read_workdays(
            environment, "ESTIMATE_MAESTRO_WORKDAYS", frozenset({0, 1, 2, 3, 4})
        ),
    )
    store = environment.get("ESTIMATE_MAESTRO_STORE", DEFAULT_STORE_PATH)
    derive_lead_in = _read_minutes(
        environment, "ESTIMATE_MAESTRO_DERIVE_LEAD_IN_MINUTES", timedelta(minutes=30)
    )
    derive_session_gap = _read_minutes(
        environment, "ESTIMATE_MAESTRO_DERIVE_SESSION_GAP_MINUTES", timedelta(hours=2)
    )
    if derive_lead_in > derive_session_gap:
        raise ValueError(
            "ESTIMATE_MAESTRO_DERIVE_LEAD_IN_MINUTES must not exceed "
            "ESTIMATE_MAESTRO_DERIVE_SESSION_GAP_MINUTES: "
            f"{derive_lead_in} > {derive_session_gap}"
        )
    return Config(
        store_path=Path(store).expanduser(),
        working_hours=working_hours,
        off_hours_session_cap=_read_minutes(
            environment, "ESTIMATE_MAESTRO_OFF_HOURS_SESSION_CAP_MINUTES", timedelta(hours=4)
        ),
        derive_lead_in=derive_lead_in,
        derive_session_gap=derive_session_gap,
        minimum_efforts_for_analysis=int(environment.get("ESTIMATE_MAESTRO_MINIMUM_EFFORTS", "5")),
    )
