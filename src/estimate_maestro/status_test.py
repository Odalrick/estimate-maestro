from datetime import UTC, datetime
from pathlib import Path

import pytest

from estimate_maestro.responses import tainted_field_names
from estimate_maestro.status import current, find_open_interval
from estimate_maestro.store import INTERVALS_LOG, Store

FROZEN = datetime(2026, 8, 24, 9, 12, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> Store:
    created = Store(tmp_path / "store")
    created.initialise()
    created.create_effort("2026-08-24-thing", {"title": "Thing", "status": "active"})
    return created


def test_nothing_open_reports_an_empty_status(store: Store):
    reported = current(store)

    assert reported.interval is None
    assert reported.since is None


def test_an_open_interval_is_found_across_efforts(store: Store):
    store.create_effort("2026-08-20-other", {"title": "Other", "status": "active"})
    store.append(
        "2026-08-20-other",
        INTERVALS_LOG,
        {"event": "clock_in", "interval": "iv-01", "slice": "sl-01", "at": FROZEN.isoformat()},
    )

    found = find_open_interval(store)

    assert found is not None
    assert found[0] == "2026-08-20-other"


def test_status_reports_the_start_timestamp_and_no_elapsed(store: Store):
    store.append(
        "2026-08-24-thing",
        INTERVALS_LOG,
        {"event": "clock_in", "interval": "iv-01", "slice": "sl-01", "at": FROZEN.isoformat()},
    )

    reported = current(store)

    assert reported.effort == "2026-08-24-thing"
    assert reported.work_slice == "sl-01"
    assert reported.since == FROZEN
    assert tainted_field_names(type(reported)) == []
