from pathlib import Path
from typing import Any

import pytest

from estimate_maestro.estimation import reference_efforts
from estimate_maestro.responses import ReferenceEffort, tainted_field_names
from estimate_maestro.store import ESTIMATES_LOG, META_FILE, Store


def add(
    store: Store,
    effort: str,
    title: str,
    likely: float,
    summary: str,
    created_at: Any = "2026-08-24T09:00:00+00:00",
) -> None:
    """Create an effort with an initial estimate.

    `created_at` is deliberately untyped: several tests store values a hand-edited
    or legacy `effort.json` can hold — a null, a number, a naive timestamp.
    """
    store.create_effort(
        effort,
        {
            "title": title,
            "kind": "mega-pull-request",
            "status": "done",
            "created_at": created_at,
        },
    )
    store.append(
        effort,
        ESTIMATES_LOG,
        {
            "pass": "initial",
            "estimate": {"scale": "points", "optimistic": 1, "likely": likely, "pessimistic": 30},
            "summary": summary,
            "slice_count": 1,
            "at": "2026-08-24T09:00:00+00:00",
        },
    )


@pytest.fixture
def store(tmp_path: Path) -> Store:
    created = Store(tmp_path / "store")
    created.initialise()
    add(
        created,
        "2026-08-01-alpha",
        "Alpha",
        15,
        "Lantern environment progression.",
        "2026-08-01T09:00:00+00:00",
    )
    add(
        created,
        "2026-08-20-beta",
        "Beta",
        8,
        "Markdown rendered into docx.",
        "2026-08-20T09:00:00+00:00",
    )
    return created


def test_reference_efforts_are_newest_first(store: Store):
    references = reference_efforts(store)

    assert [reference.effort for reference in references] == [
        "2026-08-20-beta",
        "2026-08-01-alpha",
    ]


def test_each_reference_carries_its_summary_and_triple(store: Store):
    beta = reference_efforts(store)[0]

    assert beta.summary == "Markdown rendered into docx."
    assert beta.initial.likely == 8


def test_an_effort_without_an_initial_estimate_is_omitted(store: Store):
    store.create_effort(
        "2026-08-22-gamma",
        {
            "title": "Gamma",
            "kind": "other",
            "status": "active",
            "created_at": "2026-08-22T09:00:00+00:00",
        },
    )

    assert "2026-08-22-gamma" not in [reference.effort for reference in reference_efforts(store)]


def test_the_limit_is_respected(store: Store):
    assert len(reference_efforts(store, limit=1)) == 1


def test_reference_efforts_leak_no_actuals():
    assert tainted_field_names(ReferenceEffort) == []


def test_kind_filtering_returns_only_matching_efforts(store: Store):
    store.create_effort(
        "2026-08-21-chore",
        {
            "title": "Chore",
            "kind": "chore",
            "status": "done",
            "created_at": "2026-08-21T09:00:00+00:00",
        },
    )
    store.append(
        "2026-08-21-chore",
        ESTIMATES_LOG,
        {
            "pass": "initial",
            "estimate": {"scale": "points", "optimistic": 1, "likely": 5, "pessimistic": 30},
            "summary": "A chore effort.",
            "slice_count": 1,
            "at": "2026-08-21T09:00:00+00:00",
        },
    )

    mega_prs = reference_efforts(store, kind="mega-pull-request")

    assert [reference.effort for reference in mega_prs] == [
        "2026-08-20-beta",
        "2026-08-01-alpha",
    ]
    assert "2026-08-21-chore" not in [reference.effort for reference in mega_prs]


def test_efforts_without_initial_estimates_do_not_consume_the_limit(store: Store):
    store.create_effort(
        "2026-08-21-delta",
        {
            "title": "Delta",
            "kind": "mega-pull-request",
            "status": "active",
            "created_at": "2026-08-21T09:00:00+00:00",
        },
    )
    add(
        store,
        "2026-08-22-epsilon",
        "Epsilon",
        12,
        "Another effort.",
        "2026-08-22T09:00:00+00:00",
    )

    results = reference_efforts(store, limit=2)

    assert [reference.effort for reference in results] == [
        "2026-08-22-epsilon",
        "2026-08-20-beta",
    ]


def test_newest_first_by_creation_time_not_lexical_order(store: Store):
    add(
        store,
        "2026-08-20-a-newest",
        "A Newest",
        18,
        "Created last, sorts first lexically.",
        "2026-08-20T10:00:00+00:00",
    )
    add(
        store,
        "2026-08-20-z-oldest",
        "Z Oldest",
        7,
        "Created first, sorts last lexically.",
        "2026-08-20T08:00:00+00:00",
    )

    efforts = [reference.effort for reference in reference_efforts(store)]

    assert efforts.index("2026-08-20-a-newest") < efforts.index("2026-08-20-z-oldest")


def test_one_malformed_record_does_not_prevent_other_efforts_from_returning(store: Store):
    store.create_effort(
        "2026-08-19-broken",
        {
            "title": "Broken",
            "kind": "mega-pull-request",
            "status": "done",
            "created_at": "2026-08-19T09:00:00+00:00",
        },
    )
    store.append(
        "2026-08-19-broken",
        ESTIMATES_LOG,
        {
            "pass": "initial",
            "estimate": {"scale": "points", "optimistic": 1, "pessimistic": 30},
            "summary": "Missing likely.",
            "slice_count": 1,
            "at": "2026-08-19T09:00:00+00:00",
        },
    )

    results = reference_efforts(store)

    assert len(results) == 2
    assert [reference.effort for reference in results] == [
        "2026-08-20-beta",
        "2026-08-01-alpha",
    ]
    assert "2026-08-19-broken" not in [reference.effort for reference in results]


def test_empty_final_summary_does_not_blank_initial_summary(store: Store):
    store.create_effort(
        "2026-08-19-revision",
        {
            "title": "Revision",
            "kind": "mega-pull-request",
            "status": "done",
            "created_at": "2026-08-19T09:00:00+00:00",
        },
    )
    store.append(
        "2026-08-19-revision",
        ESTIMATES_LOG,
        {
            "pass": "initial",
            "estimate": {"scale": "points", "optimistic": 1, "likely": 10, "pessimistic": 30},
            "summary": "Initial plan with details.",
            "slice_count": 1,
            "at": "2026-08-19T09:00:00+00:00",
        },
    )
    store.append(
        "2026-08-19-revision",
        ESTIMATES_LOG,
        {
            "pass": "final",
            "estimate": {"scale": "points", "optimistic": 1, "likely": 12, "pessimistic": 30},
            "summary": "",
            "slice_count": 1,
            "at": "2026-08-19T18:00:00+00:00",
        },
    )

    results = reference_efforts(store)
    revision = next(r for r in results if r.effort == "2026-08-19-revision")

    assert revision.summary == "Initial plan with details."


def test_an_effort_missing_created_at_is_returned_and_sorted_last(store: Store):
    store.create_effort(
        "2026-08-18-undated",
        {
            "title": "Undated",
            "kind": "mega-pull-request",
            "status": "done",
        },
    )
    store.append(
        "2026-08-18-undated",
        ESTIMATES_LOG,
        {
            "pass": "initial",
            "estimate": {"scale": "points", "optimistic": 1, "likely": 5, "pessimistic": 30},
            "summary": "Effort with missing created_at.",
            "slice_count": 1,
            "at": "2026-08-18T09:00:00+00:00",
        },
    )

    assert [reference.effort for reference in reference_efforts(store)] == [
        "2026-08-20-beta",
        "2026-08-01-alpha",
        "2026-08-18-undated",
    ]


def test_an_effort_with_unparseable_created_at_is_returned_and_sorted_last(store: Store):
    add(store, "2026-08-17-broken-date", "Broken Date", 9, "Unparseable.", "not-a-date")

    assert [reference.effort for reference in reference_efforts(store)] == [
        "2026-08-20-beta",
        "2026-08-01-alpha",
        "2026-08-17-broken-date",
    ]


def test_an_effort_with_a_null_created_at_is_returned_and_sorted_last(store: Store):
    add(store, "2026-08-16-null-date", "Null Date", 6, "created_at is null.", None)

    assert [reference.effort for reference in reference_efforts(store)] == [
        "2026-08-20-beta",
        "2026-08-01-alpha",
        "2026-08-16-null-date",
    ]


def test_an_effort_with_a_numeric_created_at_is_returned_and_sorted_last(store: Store):
    add(store, "2026-08-15-epoch-date", "Epoch Date", 4, "created_at is a number.", 1755000000)

    assert [reference.effort for reference in reference_efforts(store)] == [
        "2026-08-20-beta",
        "2026-08-01-alpha",
        "2026-08-15-epoch-date",
    ]


def test_an_effort_with_a_naive_created_at_is_returned_and_sorted_last(store: Store):
    add(store, "2026-08-14-naive", "Naive", 3, "No offset.", "2026-08-20T10:00:00")

    assert [reference.effort for reference in reference_efforts(store)] == [
        "2026-08-20-beta",
        "2026-08-01-alpha",
        "2026-08-14-naive",
    ]


def test_naive_and_aware_created_at_in_one_store_do_not_break_the_listing(store: Store):
    add(store, "2026-08-23-aware", "Aware", 11, "Offset present.", "2026-08-23T09:00:00+00:00")
    add(store, "2026-08-22-naive", "Naive", 2, "Offset absent.", "2026-08-22T10:00:00")

    assert [reference.effort for reference in reference_efforts(store)] == [
        "2026-08-23-aware",
        "2026-08-20-beta",
        "2026-08-01-alpha",
        "2026-08-22-naive",
    ]


def test_undated_efforts_are_ordered_by_identifier_among_themselves(store: Store):
    add(store, "2026-08-13-zulu", "Zulu", 5, "Unusable date.", "not-a-date")
    add(store, "2026-08-12-alfa", "Alfa", 5, "Unusable date.", "2026-08-12T10:00:00")

    assert [reference.effort for reference in reference_efforts(store)] == [
        "2026-08-20-beta",
        "2026-08-01-alpha",
        "2026-08-12-alfa",
        "2026-08-13-zulu",
    ]


def test_an_effort_whose_meta_is_not_an_object_is_skipped(store: Store):
    add(store, "2026-08-11-not-an-object", "Not An Object", 5, "Meta is a JSON list.")
    (store.effort_directory("2026-08-11-not-an-object") / META_FILE).write_text(
        "[1, 2, 3]\n", encoding="utf-8"
    )

    assert [reference.effort for reference in reference_efforts(store)] == [
        "2026-08-20-beta",
        "2026-08-01-alpha",
    ]


def test_an_effort_whose_meta_has_no_usable_title_is_skipped(store: Store):
    store.create_effort(
        "2026-08-10-titleless",
        {"kind": "mega-pull-request", "status": "done", "created_at": "2026-08-10T09:00:00+00:00"},
    )
    store.append(
        "2026-08-10-titleless",
        ESTIMATES_LOG,
        {
            "pass": "initial",
            "estimate": {"scale": "points", "optimistic": 1, "likely": 5, "pessimistic": 30},
            "summary": "No title in meta.",
            "slice_count": 1,
            "at": "2026-08-10T09:00:00+00:00",
        },
    )

    assert [reference.effort for reference in reference_efforts(store)] == [
        "2026-08-20-beta",
        "2026-08-01-alpha",
    ]


def test_a_corrupt_estimates_log_does_not_abort_the_listing(store: Store):
    add(store, "2026-08-09-corrupt-log", "Corrupt Log", 5, "Log is not JSON.")
    (store.effort_directory("2026-08-09-corrupt-log") / ESTIMATES_LOG).write_text(
        "{not json\n", encoding="utf-8"
    )

    assert [reference.effort for reference in reference_efforts(store)] == [
        "2026-08-20-beta",
        "2026-08-01-alpha",
    ]
