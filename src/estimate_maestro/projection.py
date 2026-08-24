from typing import Any

from estimate_maestro.models import SliceEvent


def slice_count(slice_records: list[dict[str, Any]]) -> int:
    live: set[str] = set()
    for record in slice_records:
        event = record.get("event")
        if event == SliceEvent.ADDED:
            live.add(record["slice"])
        elif event == SliceEvent.DROPPED:
            live.discard(record["slice"])
    return len(live)
