from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from estimate_maestro.config import load_config
from estimate_maestro.errors import AlreadyClockedIn, EffortAlreadyExists, NotClockedIn
from estimate_maestro.models import Estimate, MeetingParticipants
from estimate_maestro.recording import Recorder
from estimate_maestro.responses import tainted_field_names
from estimate_maestro.store import ESTIMATES_LOG, INTERVALS_LOG, SLICES_LOG, Store

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


def test_a_slice_added_after_the_effort_is_active_is_marked_in_flight(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier

    acknowledgement = recorder.add_slice(effort, "Asset progression")

    inserted = recorder.store.read(effort, SLICES_LOG)[-1]

    assert acknowledgement.recorded == "slice"
    assert inserted["phase"] == "in_flight"
    assert inserted["title"] == "Asset progression"


def test_closing_a_slice_records_the_pull_request(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier
    work_slice = recorder.store.read(effort, SLICES_LOG)[0]["slice"]

    recorder.close_slice(effort, work_slice, pull_request="add-comply#1104")

    closed = recorder.store.read(effort, SLICES_LOG)[-1]

    assert closed["event"] == "closed"
    assert closed["pull_request"] == "add-comply#1104"
    assert recorder.store.read_meta(effort)["pull_requests"] == ["add-comply#1104"]


def test_dropping_a_slice_removes_it_from_the_count(recorder, plan):
    from estimate_maestro.projection import slice_count as count

    effort = start(recorder, plan, ["Enum", "Client"]).identifier
    work_slice = recorder.store.read(effort, SLICES_LOG)[1]["slice"]

    recorder.drop_slice(effort, work_slice, reason="Already implemented.")

    assert count(recorder.store.read(effort, SLICES_LOG)) == 1


def test_renaming_a_slice_appends_rather_than_rewrites(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier
    work_slice = recorder.store.read(effort, SLICES_LOG)[0]["slice"]

    recorder.rename_slice(effort, work_slice, "Tier enum expansion")

    records = recorder.store.read(effort, SLICES_LOG)

    assert len(records) == 2
    assert records[-1]["event"] == "renamed"
    assert records[0]["title"] == "Enum"


def test_closing_a_slice_twice_with_the_same_pull_request_deduplicates(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier
    work_slice = recorder.store.read(effort, SLICES_LOG)[0]["slice"]

    recorder.close_slice(effort, work_slice, pull_request="add-comply#1104")
    recorder.close_slice(effort, work_slice, pull_request="add-comply#1104")

    assert recorder.store.read_meta(effort)["pull_requests"] == ["add-comply#1104"]


def test_closing_an_unknown_slice_raises_unknown_slice(recorder, plan):
    from estimate_maestro.errors import UnknownSlice

    effort = start(recorder, plan, ["Enum"]).identifier

    with pytest.raises(UnknownSlice):
        recorder.close_slice(effort, "sl-9999", pull_request="add-comply#1104")


def test_dropping_an_unknown_slice_raises_unknown_slice(recorder, plan):
    from estimate_maestro.errors import UnknownSlice

    effort = start(recorder, plan, ["Enum"]).identifier

    with pytest.raises(UnknownSlice):
        recorder.drop_slice(effort, "sl-9999", reason="Already implemented.")


def test_renaming_an_unknown_slice_raises_unknown_slice(recorder, plan):
    from estimate_maestro.errors import UnknownSlice

    effort = start(recorder, plan, ["Enum"]).identifier

    with pytest.raises(UnknownSlice):
        recorder.rename_slice(effort, "sl-9999", "New title")


def test_clocking_in_records_an_open_interval(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier

    acknowledgement = recorder.clock_in(effort)

    record = recorder.store.read(effort, INTERVALS_LOG)[-1]

    assert acknowledgement.recorded == "interval"
    assert record["event"] == "clock_in"
    assert record["kind"] == "work"
    assert "stop" not in record


def test_clocking_in_twice_is_refused(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier
    recorder.clock_in(effort)

    with pytest.raises(AlreadyClockedIn):
        recorder.clock_in(effort)


def test_clocking_in_twice_is_refused_across_efforts(recorder, plan):
    first_effort = start(recorder, plan, ["Enum"]).identifier
    second_effort = recorder.start_effort(
        title="Nimbus Onboarding Flow",
        kind="mega-pull-request",
        plan_path=plan,
        summary="Nimbus onboarding gains a guided flow.",
        estimate=Estimate(optimistic=3, likely=5, pessimistic=9),
        rationale="Sized similarly to the tiers effort.",
        work_slices=["Enum"],
    ).identifier
    recorder.clock_in(first_effort)

    with pytest.raises(AlreadyClockedIn):
        recorder.clock_in(second_effort)


def test_clocking_in_against_an_unknown_slice_is_refused(recorder, plan):
    from estimate_maestro.errors import UnknownSlice

    effort = start(recorder, plan, ["Enum"]).identifier

    with pytest.raises(UnknownSlice):
        recorder.clock_in(effort, work_slice="sl-9999")


def test_clocking_out_without_an_open_interval_is_refused(recorder, plan):
    start(recorder, plan, ["Enum"])

    with pytest.raises(NotClockedIn):
        recorder.clock_out()


def test_clocking_out_closes_the_open_interval_as_manual(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier
    recorder.clock_in(effort)

    recorder.clock_out(at=FROZEN + timedelta(hours=2))

    record = recorder.store.read(effort, INTERVALS_LOG)[-1]

    assert record["event"] == "clock_out"
    assert record["provenance"] == "manual"
    assert record["at"] == (FROZEN + timedelta(hours=2)).isoformat()


def test_clamped_clock_out_stops_at_the_end_of_the_workday(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier
    recorder.clock_in(effort)

    recorder.clock_out_clamped(last_activity=FROZEN + timedelta(days=3))

    record = recorder.store.read(effort, INTERVALS_LOG)[-1]

    assert record["provenance"] == "clamped"
    assert record["at"].startswith("2026-08-24T17:00:00")


def test_a_meeting_records_its_participants(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier

    recorder.clock_in(
        effort,
        kind="meeting",
        meeting=MeetingParticipants(internal=2, external=1, names=["me", "manager", "sales"]),
    )

    record = recorder.store.read(effort, INTERVALS_LOG)[-1]

    assert record["kind"] == "meeting"
    assert record["meeting"]["internal"] == 2
    assert record["meeting"]["external"] == 1


def test_participants_can_be_attached_after_the_fact(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier
    interval = recorder.clock_in(effort).identifier

    recorder.annotate_interval(
        effort, interval, meeting=MeetingParticipants(internal=3, external=0)
    )

    record = recorder.store.read(effort, INTERVALS_LOG)[-1]

    assert record["event"] == "annotate"
    assert record["meeting"]["internal"] == 3


def test_repairing_an_interval_appends_rather_than_rewrites(recorder, plan):
    effort = start(recorder, plan, ["Enum"]).identifier
    interval = recorder.clock_in(effort).identifier
    recorder.clock_out(at=FROZEN + timedelta(hours=2))

    recorder.repair_interval(effort, interval, start=FROZEN + timedelta(minutes=90))

    records = recorder.store.read(effort, INTERVALS_LOG)

    assert records[-1]["event"] == "repair"
    assert records[0]["at"] == FROZEN.isoformat()


def test_an_absence_is_recorded_at_the_store_root(recorder, plan):
    from estimate_maestro.models import AbsenceKind

    start(recorder, plan, ["Enum"])

    recorder.record_absence(
        FROZEN, FROZEN + timedelta(hours=1), AbsenceKind.APPOINTMENT, note="dentist"
    )

    absences = recorder.store.read_absences()

    assert absences[0]["kind"] == "appointment"
    assert absences[0]["note"] == "dentist"


def test_harvesting_records_commits_against_the_slice(recorder, plan, tmp_path):
    import subprocess

    from estimate_maestro.store import COMMITS_LOG

    effort = start(recorder, plan, ["Enum"]).identifier
    work_slice = recorder.store.read(effort, SLICES_LOG)[0]["slice"]
    repository = tmp_path / "repo"
    repository.mkdir()
    for arguments in (
        ["init", "-b", "main"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
    ):
        subprocess.run(["git", *arguments], cwd=repository, check=True, capture_output=True)
    (repository / "a.txt").write_text("a\n")
    subprocess.run(["git", "add", "."], cwd=repository, check=True, capture_output=True)
    stamp = FROZEN.isoformat()
    subprocess.run(
        ["git", "commit", "-m", "work"],
        cwd=repository,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_DATE": stamp,
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
        },
    )

    recorder.harvest_commits(
        effort,
        work_slice,
        repository,
        since=FROZEN - timedelta(days=1),
        until=FROZEN + timedelta(days=1),
    )

    commits = recorder.store.read(effort, COMMITS_LOG)

    assert commits[0]["subject"] == "work"
    assert commits[0]["slice"] == work_slice
    assert commits[0]["vcs"] == "git"
    assert commits[0]["repository"] == "repo"
    assert recorder.store.read_meta(effort)["repositories"] == ["repo"]


def test_remapping_appends_rather_than_overwriting(recorder, plan):
    from estimate_maestro.store import COMMITS_LOG

    effort = start(recorder, plan, ["Enum"]).identifier

    recorder.remap_commits(effort, old="aaaa", new="bbbb", reason="rebase")

    remap = recorder.store.read(effort, COMMITS_LOG)[-1]

    assert remap == {
        "event": "remap",
        "old": "aaaa",
        "new": "bbbb",
        "reason": "rebase",
        "at": FROZEN.isoformat(),
    }
