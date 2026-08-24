from pathlib import Path

import pytest

from estimate_maestro.estimation import reference_efforts
from estimate_maestro.responses import ReferenceEffort, tainted_field_names
from estimate_maestro.store import ESTIMATES_LOG, Store


def add(
    store: Store,
    effort: str,
    title: str,
    likely: float,
    summary: str,
    created_at: str = "2026-08-24T09:00:00+00:00",
) -> None:
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
        "Squidex environment progression.",
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

    efforts = [reference.effort for reference in reference_efforts(store)]

    assert "2026-08-18-undated" in efforts
    assert efforts.index("2026-08-18-undated") > efforts.index("2026-08-20-beta")


def test_an_effort_with_unparseable_created_at_is_returned_and_sorted_last(store: Store):
    store.create_effort(
        "2026-08-17-broken-date",
        {
            "title": "Broken Date",
            "kind": "mega-pull-request",
            "status": "done",
            "created_at": "not-a-date",
        },
    )
    store.append(
        "2026-08-17-broken-date",
        ESTIMATES_LOG,
        {
            "pass": "initial",
            "estimate": {"scale": "points", "optimistic": 1, "likely": 9, "pessimistic": 30},
            "summary": "Effort with unparseable created_at.",
            "slice_count": 1,
            "at": "2026-08-17T09:00:00+00:00",
        },
    )

    efforts = [reference.effort for reference in reference_efforts(store)]

    assert "2026-08-17-broken-date" in efforts
    assert efforts.index("2026-08-17-broken-date") > efforts.index("2026-08-20-beta")
