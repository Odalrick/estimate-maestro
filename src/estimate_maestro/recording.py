import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from estimate_maestro.config import Config
from estimate_maestro.errors import EffortAlreadyExists, UnknownSlice
from estimate_maestro.identifiers import effort_identifier, new_identifier
from estimate_maestro.models import (
    EffortStatus,
    Estimate,
    EstimatePass,
    SliceEvent,
    SlicePhase,
)
from estimate_maestro.projection import live_slices, slice_count
from estimate_maestro.responses import Acknowledgement
from estimate_maestro.store import ESTIMATES_LOG, SLICES_LOG, Store


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
