from pathlib import Path

import pytest

from estimate_maestro.estimation import reference_efforts
from estimate_maestro.responses import ReferenceEffort, tainted_field_names
from estimate_maestro.store import ESTIMATES_LOG, Store


def add(store: Store, effort: str, title: str, likely: float, summary: str) -> None:
    store.create_effort(effort, {"title": title, "kind": "mega-pull-request", "status": "done"})
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
    add(created, "2026-08-01-alpha", "Alpha", 15, "Squidex environment progression.")
    add(created, "2026-08-20-beta", "Beta", 8, "Markdown rendered into docx.")
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
    store.create_effort("2026-08-22-gamma", {"title": "Gamma", "kind": "other", "status": "active"})

    assert "2026-08-22-gamma" not in [reference.effort for reference in reference_efforts(store)]


def test_the_limit_is_respected(store: Store):
    assert len(reference_efforts(store, limit=1)) == 1


def test_reference_efforts_leak_no_actuals():
    assert tainted_field_names(ReferenceEffort) == []
