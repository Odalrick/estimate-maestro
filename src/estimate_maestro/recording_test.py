from datetime import UTC, datetime
from pathlib import Path

import pytest

from estimate_maestro.config import load_config
from estimate_maestro.errors import EffortAlreadyExists
from estimate_maestro.models import Estimate
from estimate_maestro.recording import Recorder
from estimate_maestro.responses import tainted_field_names
from estimate_maestro.store import ESTIMATES_LOG, SLICES_LOG, Store

FROZEN = datetime(2026, 8, 24, 9, 14, tzinfo=UTC)


@pytest.fixture
def recorder(tmp_path: Path) -> Recorder:
    store = Store(tmp_path / "store")
    store.initialise()
    counter = iter(range(1, 1000))
    return Recorder(
        store=store,
        config=load_config({"ESTIMATE_MAESTRO_STORE": str(tmp_path / "store")}),
        now=lambda: FROZEN,
        make_identifier=lambda prefix: f"{prefix}-{next(counter):04d}",
    )


@pytest.fixture
def plan(tmp_path: Path) -> Path:
    written = tmp_path / ".PR.md"
    written.write_text("# the plan\n")
    return written


def start(recorder: Recorder, plan: Path, work_slices: list[str]):
    return recorder.start_effort(
        title="Squidex Environment Tiers",
        kind="mega-pull-request",
        plan_path=plan,
        summary="Squidex environments gain a tier progression.",
        estimate=Estimate(optimistic=3, likely=5, pessimistic=9),
        rationale="About the size of the domain-display effort.",
        work_slices=work_slices,
    )


def test_starting_an_effort_returns_an_acknowledgement_and_nothing_else(recorder, plan):
    acknowledgement = start(recorder, plan, ["Enum", "Server reads", "Client"])

    assert acknowledgement.recorded == "effort"
    assert acknowledgement.identifier == "2026-08-24-squidex-environment-tiers"
    assert tainted_field_names(type(acknowledgement)) == []


def test_the_plan_slices_are_recorded_as_planning_phase(recorder, plan):
    effort = start(recorder, plan, ["Enum", "Server reads", "Client"]).identifier

    records = recorder.store.read(effort, SLICES_LOG)

    assert [record["event"] for record in records] == ["added"] * 3
    assert {record["phase"] for record in records} == {"planning"}


def test_the_initial_estimate_captures_the_slice_count_automatically(recorder, plan):
    effort = start(recorder, plan, ["Enum", "Server reads", "Client"]).identifier

    initial = recorder.store.read(effort, ESTIMATES_LOG)[0]

    assert initial["pass"] == "initial"
    assert initial["slice_count"] == 3
    assert initial["estimate"]["likely"] == 5
    assert initial["summary"].startswith("Squidex environments")


def test_the_plan_artefact_is_snapshotted(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier

    initial = recorder.store.read(effort, ESTIMATES_LOG)[0]
    snapshot = recorder.store.effort_directory(effort) / "snapshots" / initial["snapshot"]

    assert snapshot.read_text() == "# the plan\n"


def test_the_effort_becomes_active_once_started(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier

    assert recorder.store.read_meta(effort)["status"] == "active"


def test_a_revision_appends_a_second_pass(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier

    recorder.record_revision(
        effort, Estimate(optimistic=6, likely=9, pessimistic=15), "Asset progression appeared."
    )

    passes = [record["pass"] for record in recorder.store.read(effort, ESTIMATES_LOG)]

    assert passes == ["initial", "revision"]


def test_the_final_pass_snapshots_the_final_plan_and_recounts_slices(recorder, plan, tmp_path):
    effort = start(recorder, plan, ["Enum", "Server reads", "Client"]).identifier
    final_plan = tmp_path / "final.PR.md"
    final_plan.write_text("# six slices\n")

    recorder.record_final_plan(
        effort,
        plan_path=final_plan,
        summary="Turned out to be an asset progression problem.",
        estimate=Estimate(optimistic=10, likely=13, pessimistic=20),
        rationale="Knowing the scope, this was a 13.",
    )

    final = recorder.store.read(effort, ESTIMATES_LOG)[-1]

    assert final["pass"] == "final"
    assert final["slice_count"] == 3
    assert final["snapshot"].startswith("final-")


def test_finishing_an_effort_marks_it_done(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier

    recorder.finish_effort(effort)

    assert recorder.store.read_meta(effort)["status"] == "done"


def test_a_failed_start_leaves_no_wreckage_and_permits_a_retry(recorder, tmp_path):
    missing_plan = tmp_path / "missing.PR.md"

    with pytest.raises(FileNotFoundError):
        start(recorder, missing_plan, ["Enum"])

    assert recorder.store.list_efforts() == []

    retried_plan = tmp_path / "retry.PR.md"
    retried_plan.write_text("# retried\n")

    acknowledgement = start(recorder, retried_plan, ["Enum"])

    assert acknowledgement.identifier == "2026-08-24-squidex-environment-tiers"
    assert recorder.store.list_efforts() == [acknowledgement.identifier]


def test_starting_an_effort_twice_raises_effort_already_exists(recorder, plan):
    first = start(recorder, plan, ["Enum"]).identifier

    with pytest.raises(EffortAlreadyExists):
        start(recorder, plan, ["Enum", "Extra"])

    slices = recorder.store.read(first, SLICES_LOG)
    assert [record["title"] for record in slices] == ["Enum"]

    estimates = recorder.store.read(first, ESTIMATES_LOG)
    assert len(estimates) == 1
    assert recorder.store.read_meta(first)["status"] == "active"
