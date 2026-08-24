from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from estimate_maestro.config import Config
from estimate_maestro.identifiers import effort_identifier, new_identifier
from estimate_maestro.models import (
    EffortStatus,
    Estimate,
    EstimatePass,
    SliceEvent,
    SlicePhase,
)
from estimate_maestro.projection import slice_count
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
        self.store.create_effort(
            effort,
            {
                "title": title,
                "kind": kind,
                "status": EffortStatus.PLANNING,
                "created_at": moment.isoformat(),
                "repositories": [],
                "pull_requests": [],
            },
        )
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
        meta = self.store.read_meta(effort)
        meta["status"] = EffortStatus.ACTIVE
        self.store.write_meta(effort, meta)
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
        meta = self.store.read_meta(effort)
        meta["status"] = EffortStatus.DONE
        self.store.write_meta(effort, meta)
        return Acknowledgement(recorded="effort", identifier=effort)
