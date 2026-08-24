import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from estimate_maestro.clock import clamp_stop
from estimate_maestro.config import Config
from estimate_maestro.errors import (
    AlreadyClockedIn,
    EffortAlreadyExists,
    NotClockedIn,
    UnknownSlice,
)
from estimate_maestro.identifiers import effort_identifier, new_identifier
from estimate_maestro.models import (
    AbsenceKind,
    CommitEvent,
    EffortStatus,
    Estimate,
    EstimatePass,
    IntervalEvent,
    IntervalKind,
    MeetingParticipants,
    Provenance,
    SliceEvent,
    SlicePhase,
    Vcs,
)
from estimate_maestro.projection import live_slices, slice_count
from estimate_maestro.responses import Acknowledgement
from estimate_maestro.status import find_open_interval
from estimate_maestro.store import COMMITS_LOG, ESTIMATES_LOG, INTERVALS_LOG, SLICES_LOG, Store
from estimate_maestro.vcs import commits_between, detect_repository


def _now() -> datetime:
    return datetime.now().astimezone()


class Recorder:
    def __init__(
        self,
        store: Store,
        config: Config,
        now: Callable[[], datetime] = _now,
        make_identifier: Callable[[str], str] = new_identifier,
    ):
        self.store = store
        self.config = config
        self.now = now
        self.make_identifier = make_identifier

    def _append_estimate(
        self,
        effort: str,
        which_pass: EstimatePass,
        estimate: Estimate,
        rationale: str,
        summary: str,
        snapshot: str | None,
        count: int,
    ) -> str:
        identifier = self.make_identifier("es")
        self.store.append(
            effort,
            ESTIMATES_LOG,
            {
                "identifier": identifier,
                "pass": which_pass,
                "at": self.now(),
                "estimate": estimate.model_dump(mode="json"),
                "slice_count": count,
                "snapshot": snapshot,
                "summary": summary,
                "rationale": rationale,
            },
        )
        return identifier

    def start_effort(
        self,
        title: str,
        kind: str,
        plan_path: Path,
        summary: str,
        estimate: Estimate,
        rationale: str,
        work_slices: list[str],
    ) -> Acknowledgement:
        moment = self.now()
        effort = effort_identifier(moment.date(), title)
        meta = {
            "title": title,
            "kind": kind,
            "status": EffortStatus.PLANNING,
            "created_at": moment.isoformat(),
            "repositories": [],
            "pull_requests": [],
        }
        try:
            self.store.create_effort(effort, meta)
        except FileExistsError as error:
            raise EffortAlreadyExists(effort) from error
        try:
            for title_of_slice in work_slices:
                self.store.append(
                    effort,
                    SLICES_LOG,
                    {
                        "event": SliceEvent.ADDED,
                        "slice": self.make_identifier("sl"),
                        "title": title_of_slice,
                        "phase": SlicePhase.PLANNING,
                        "at": moment,
                    },
                )
            snapshot = self.store.snapshot(effort, plan_path, label="initial")
            self._append_estimate(
                effort,
                EstimatePass.INITIAL,
                estimate,
                rationale,
                summary,
                snapshot,
                len(work_slices),
            )
            meta["status"] = EffortStatus.ACTIVE
            self.store.write_meta(effort, meta)
        except Exception:
            shutil.rmtree(self.store.effort_directory(effort))
            raise
        return Acknowledgement(recorded="effort", identifier=effort)

    def record_revision(
        self, effort: str, estimate: Estimate, rationale: str, summary: str = ""
    ) -> Acknowledgement:
        identifier = self._append_estimate(
            effort,
            EstimatePass.REVISION,
            estimate,
            rationale,
            summary,
            None,
            slice_count(self.store.read(effort, SLICES_LOG)),
        )
        return Acknowledgement(recorded="estimate", identifier=identifier)

    def record_final_plan(
        self, effort: str, plan_path: Path, summary: str, estimate: Estimate, rationale: str
    ) -> Acknowledgement:
        snapshot = self.store.snapshot(effort, plan_path, label="final")
        identifier = self._append_estimate(
            effort,
            EstimatePass.FINAL,
            estimate,
            rationale,
            summary,
            snapshot,
            slice_count(self.store.read(effort, SLICES_LOG)),
        )
        return Acknowledgement(recorded="estimate", identifier=identifier)

    def finish_effort(self, effort: str) -> Acknowledgement:
        def mark_done(meta: dict[str, Any]) -> None:
            meta["status"] = EffortStatus.DONE

        self.store.update_meta(effort, mark_done)
        return Acknowledgement(recorded="effort", identifier=effort)

    def _append_slice_event(self, effort: str, record: dict[str, Any]) -> Acknowledgement:
        to_append = {**record, "at": self.now()}
        self.store.append(effort, SLICES_LOG, to_append)
        return Acknowledgement(recorded="slice", identifier=to_append["slice"])

    def add_slice(self, effort: str, title: str) -> Acknowledgement:
        status = self.store.read_meta(effort)["status"]
        phase = SlicePhase.IN_FLIGHT if status == EffortStatus.ACTIVE else SlicePhase.PLANNING
        return self._append_slice_event(
            effort,
            {
                "event": SliceEvent.ADDED,
                "slice": self.make_identifier("sl"),
                "title": title,
                "phase": phase,
            },
        )

    def close_slice(self, effort: str, work_slice: str, pull_request: str) -> Acknowledgement:
        slice_records = self.store.read(effort, SLICES_LOG)
        if work_slice not in live_slices(slice_records):
            raise UnknownSlice(work_slice)

        def add_pull_request(meta: dict[str, Any]) -> None:
            if pull_request not in meta["pull_requests"]:
                meta["pull_requests"].append(pull_request)

        self.store.update_meta(effort, add_pull_request)
        return self._append_slice_event(
            effort,
            {"event": SliceEvent.CLOSED, "slice": work_slice, "pull_request": pull_request},
        )

    def drop_slice(self, effort: str, work_slice: str, reason: str) -> Acknowledgement:
        slice_records = self.store.read(effort, SLICES_LOG)
        if work_slice not in live_slices(slice_records):
            raise UnknownSlice(work_slice)
        return self._append_slice_event(
            effort, {"event": SliceEvent.DROPPED, "slice": work_slice, "reason": reason}
        )

    def rename_slice(self, effort: str, work_slice: str, title: str) -> Acknowledgement:
        slice_records = self.store.read(effort, SLICES_LOG)
        if work_slice not in live_slices(slice_records):
            raise UnknownSlice(work_slice)
        return self._append_slice_event(
            effort, {"event": SliceEvent.RENAMED, "slice": work_slice, "title": title}
        )

    def clock_in(
        self,
        effort: str,
        work_slice: str | None = None,
        kind: IntervalKind = IntervalKind.WORK,
        meeting: MeetingParticipants | None = None,
        note: str | None = None,
    ) -> Acknowledgement:
        if find_open_interval(self.store) is not None:
            raise AlreadyClockedIn("an interval is already open; clock out first")
        if work_slice is not None:
            slice_records = self.store.read(effort, SLICES_LOG)
            if work_slice not in live_slices(slice_records):
                raise UnknownSlice(work_slice)
        interval = self.make_identifier("iv")
        record: dict[str, Any] = {
            "event": IntervalEvent.CLOCK_IN,
            "interval": interval,
            "slice": work_slice,
            "kind": kind,
            "at": self.now(),
        }
        if meeting is not None:
            record["meeting"] = meeting.model_dump(mode="json")
        if note is not None:
            record["note"] = note
        self.store.append(effort, INTERVALS_LOG, record)
        return Acknowledgement(recorded="interval", identifier=interval)

    def _close(self, stop: datetime, provenance: Provenance, note: str | None) -> Acknowledgement:
        found = find_open_interval(self.store)
        if found is None:
            raise NotClockedIn("no interval is open")
        effort, opened = found
        record: dict[str, Any] = {
            "event": IntervalEvent.CLOCK_OUT,
            "interval": opened["interval"],
            "provenance": provenance,
            "at": stop,
        }
        if note is not None:
            record["note"] = note
        self.store.append(effort, INTERVALS_LOG, record)
        return Acknowledgement(recorded="interval", identifier=opened["interval"])

    def clock_out(self, at: datetime | None = None, note: str | None = None) -> Acknowledgement:
        return self._close(at or self.now(), Provenance.MANUAL, note)

    def clock_out_clamped(
        self, last_activity: datetime, note: str | None = None
    ) -> Acknowledgement:
        found = find_open_interval(self.store)
        if found is None:
            raise NotClockedIn("no interval is open")
        _, opened = found
        started = datetime.fromisoformat(opened["at"])
        return self._close(
            clamp_stop(started, last_activity, self.config), Provenance.CLAMPED, note
        )

    def annotate_interval(
        self,
        effort: str,
        interval: str,
        meeting: MeetingParticipants | None = None,
        note: str | None = None,
    ) -> Acknowledgement:
        record: dict[str, Any] = {
            "event": IntervalEvent.ANNOTATE,
            "interval": interval,
            "at": self.now(),
        }
        if meeting is not None:
            record["meeting"] = meeting.model_dump(mode="json")
        if note is not None:
            record["note"] = note
        self.store.append(effort, INTERVALS_LOG, record)
        return Acknowledgement(recorded="interval", identifier=interval)

    def repair_interval(
        self,
        effort: str,
        interval: str,
        start: datetime | None = None,
        stop: datetime | None = None,
    ) -> Acknowledgement:
        record: dict[str, Any] = {
            "event": IntervalEvent.REPAIR,
            "interval": interval,
            "provenance": Provenance.REPAIRED,
            "at": self.now(),
        }
        if start is not None:
            record["start"] = start
        if stop is not None:
            record["stop"] = stop
        self.store.append(effort, INTERVALS_LOG, record)
        return Acknowledgement(recorded="interval", identifier=interval)

    def record_absence(
        self, start: datetime, stop: datetime, kind: AbsenceKind, note: str | None = None
    ) -> Acknowledgement:
        identifier = self.make_identifier("ab")
        record: dict[str, Any] = {
            "identifier": identifier,
            "start": start,
            "stop": stop,
            "kind": kind,
            "at": self.now(),
        }
        if note is not None:
            record["note"] = note
        self.store.append_absence(record)
        return Acknowledgement(recorded="absence", identifier=identifier)

    def harvest_commits(
        self, effort: str, work_slice: str | None, path: Path, since: datetime, until: datetime
    ) -> Acknowledgement:
        reference = detect_repository(path)
        if reference is None:
            return Acknowledgement(recorded="no_repository", identifier="none")
        for commit in commits_between(path, since, until):
            self.store.append(
                effort,
                COMMITS_LOG,
                {
                    "event": CommitEvent.HARVESTED,
                    "vcs": reference.vcs,
                    "repository": reference.repository,
                    "reference": reference.reference,
                    "slice": work_slice,
                    "identifier": commit.identifier,
                    "subject": commit.subject,
                    "authored_at": commit.authored_at,
                    "files_changed": commit.files_changed,
                    "insertions": commit.insertions,
                    "deletions": commit.deletions,
                },
            )

        def add_repository(meta: dict[str, Any]) -> None:
            if reference.repository not in meta["repositories"]:
                meta["repositories"].append(reference.repository)

        self.store.update_meta(effort, add_repository)
        return Acknowledgement(recorded="commits", identifier=effort)

    def record_landed_commit(
        self, effort: str, work_slice: str | None, repository: str, identifier: str
    ) -> Acknowledgement:
        self.store.append(
            effort,
            COMMITS_LOG,
            {
                "event": CommitEvent.LANDED,
                "vcs": Vcs.GIT,
                "repository": repository,
                "slice": work_slice,
                "identifier": identifier,
                "at": self.now(),
            },
        )
        return Acknowledgement(recorded="commit", identifier=identifier)

    def remap_commits(self, effort: str, old: str, new: str, reason: str) -> Acknowledgement:
        self.store.append(
            effort,
            COMMITS_LOG,
            {
                "event": CommitEvent.REMAP,
                "old": old,
                "new": new,
                "reason": reason,
                "at": self.now(),
            },
        )
        return Acknowledgement(recorded="remap", identifier=new)
