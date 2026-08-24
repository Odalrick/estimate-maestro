from typing import Any

from estimate_maestro.models import SliceEvent


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
