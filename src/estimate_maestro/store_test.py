from datetime import UTC, datetime
from pathlib import Path

import pytest

from estimate_maestro.store import ESTIMATES_LOG, Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    created = Store(tmp_path / "store")
    created.initialise()
    return created


def test_creating_an_effort_makes_a_directory_with_metadata(store: Store):
    store.create_effort("2026-08-24-thing", {"title": "Thing", "status": "planning"})

    assert store.effort_directory("2026-08-24-thing").is_dir()
    assert store.read_meta("2026-08-24-thing")["title"] == "Thing"


def test_appended_records_read_back_in_order(store: Store):
    store.create_effort("2026-08-24-thing", {"title": "Thing"})
    store.append("2026-08-24-thing", ESTIMATES_LOG, {"pass": "initial"})
    store.append("2026-08-24-thing", ESTIMATES_LOG, {"pass": "final"})

    passes = [record["pass"] for record in store.read("2026-08-24-thing", ESTIMATES_LOG)]

    assert passes == ["initial", "final"]


def test_reading_a_log_that_does_not_exist_yet_gives_an_empty_list(store: Store):
    store.create_effort("2026-08-24-thing", {"title": "Thing"})

    assert store.read("2026-08-24-thing", ESTIMATES_LOG) == []


def test_datetimes_are_serialised_as_iso_8601_with_an_offset(store: Store):
    store.create_effort("2026-08-24-thing", {"title": "Thing"})
    store.append(
        "2026-08-24-thing", ESTIMATES_LOG, {"at": datetime(2026, 8, 24, 9, 14, tzinfo=UTC)}
    )

    line = (store.effort_directory("2026-08-24-thing") / ESTIMATES_LOG).read_text()

    assert "2026-08-24T09:14:00+00:00" in line


def test_snapshots_copy_the_plan_artefact_under_a_labelled_name(store: Store, tmp_path: Path):
    store.create_effort("2026-08-24-thing", {"title": "Thing"})
    plan = tmp_path / ".PR.md"
    plan.write_text("# the plan\n")

    name = store.snapshot("2026-08-24-thing", plan, label="initial")

    assert name.startswith("initial-")
    assert (
        store.effort_directory("2026-08-24-thing") / "snapshots" / name
    ).read_text() == "# the plan\n"


def test_absences_live_at_the_store_root_not_inside_an_effort(store: Store):
    store.append_absence({"kind": "vacation"})

    assert store.read_absences() == [{"kind": "vacation"}]
    assert (store.root / "absences.jsonl").exists()


def test_listing_efforts_returns_them_sorted(store: Store):
    store.create_effort("2026-08-24-b", {"title": "B"})
    store.create_effort("2026-08-01-a", {"title": "A"})

    assert store.list_efforts() == ["2026-08-01-a", "2026-08-24-b"]
