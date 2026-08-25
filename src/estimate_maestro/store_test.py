from datetime import UTC, datetime
from pathlib import Path

import pytest

from estimate_maestro.errors import UnknownEffort
from estimate_maestro.store import ESTIMATES_LOG, MalformedRecord, Store, _encode


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


def test_read_lines_raises_with_line_number_for_malformed_record(store: Store):
    store.create_effort("2026-08-24-thing", {"title": "Thing"})
    log_path = store.effort_directory("2026-08-24-thing") / ESTIMATES_LOG
    log_path.write_text('{"pass": "good"}\n{broken json here\n{"pass": "also good"}\n')

    with pytest.raises(MalformedRecord) as exc_info:
        store.read("2026-08-24-thing", ESTIMATES_LOG)

    # Path and line together: the effort identifier already contains a "2", so a
    # bare substring check passes on any line number at all.
    assert str(exc_info.value) == f"malformed JSON at {log_path}:2"


def test_encode_raises_type_error_for_unsupported_type():
    with pytest.raises(TypeError):
        _encode(object())


def test_appending_to_an_effort_that_does_not_exist_is_refused(store: Store):
    with pytest.raises(UnknownEffort) as exc_info:
        store.append("2026-08-24-thnig", ESTIMATES_LOG, {"pass": "initial"})

    assert str(exc_info.value) == "unknown effort: 2026-08-24-thnig"
    assert not store.effort_directory("2026-08-24-thnig").exists()


def test_an_absence_can_be_recorded_before_any_effort_exists(tmp_path: Path):
    fresh = Store(tmp_path / "untouched")

    fresh.append_absence({"kind": "vacation"})

    assert fresh.read_absences() == [{"kind": "vacation"}]
