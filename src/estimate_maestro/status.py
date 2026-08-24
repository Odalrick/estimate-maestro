from datetime import datetime
from typing import Any

from estimate_maestro.projection import open_interval
from estimate_maestro.responses import CurrentStatus
from estimate_maestro.store import INTERVALS_LOG, Store


def find_open_interval(store: Store) -> tuple[str, dict[str, Any]] | None:
    for effort in store.list_efforts():
        opened = open_interval(store.read(effort, INTERVALS_LOG))
        if opened is not None:
            return effort, opened
    return None


def current(store: Store) -> CurrentStatus:
    found = find_open_interval(store)
    if found is None:
        return CurrentStatus()
    effort, opened = found
    return CurrentStatus(
        effort=effort,
        work_slice=opened.get("slice"),
        interval=opened["interval"],
        since=datetime.fromisoformat(opened["at"]),
    )
