import os
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel

from estimate_maestro.calibration import (
    EffortDetail,
    EffortRow,
    Summary,
    effort_detail,
    effort_table,
    summary,
)
from estimate_maestro.config import Config, load_config
from estimate_maestro.estimation import reference_efforts
from estimate_maestro.models import AbsenceKind, Estimate, IntervalKind, MeetingParticipants
from estimate_maestro.recording import Recorder
from estimate_maestro.responses import (
    Acknowledgement,
    CurrentStatus,
    ReferenceEffort,
    ToolCategory,
)
from estimate_maestro.status import current
from estimate_maestro.store import Store

RECORDING_TOOLS = (
    "start_effort",
    "add_slice",
    "close_slice",
    "drop_slice",
    "rename_slice",
    "clock_in",
    "clock_out",
    "annotate_interval",
    "repair_interval",
    "record_absence",
    "record_revision",
    "record_final_plan",
    "harvest_commits",
    "record_landed_commit",
    "remap_commits",
    "finish_effort",
)

TOOL_CATEGORIES: dict[str, ToolCategory] = {
    **{name: ToolCategory.RECORDING for name in RECORDING_TOOLS},
    "reference_efforts": ToolCategory.ESTIMATION,
    "current": ToolCategory.STATUS,
    "effort_table": ToolCategory.CALIBRATION,
    "effort_detail": ToolCategory.CALIBRATION,
    "summary": ToolCategory.CALIBRATION,
}

TOOL_RESPONSES: dict[str, type[BaseModel]] = {
    **{name: Acknowledgement for name in RECORDING_TOOLS},
    "reference_efforts": ReferenceEffort,
    "current": CurrentStatus,
    "effort_table": EffortRow,
    "effort_detail": EffortDetail,
    "summary": Summary,
}


def build_server(store: Store, config: Config) -> MCPServer:
    server = MCPServer("maestro-estimate")
    recorder = Recorder(store=store, config=config)

    @server.tool()
    def start_effort(
        title: str,
        kind: str,
        plan_path: str,
        summary_text: str,
        optimistic: float,
        likely: float,
        pessimistic: float,
        rationale: str,
        work_slices: list[str],
    ) -> Acknowledgement:
        """Create an effort from a plan artefact and an initial PERT estimate."""
        return recorder.start_effort(
            title=title,
            kind=kind,
            plan_path=Path(plan_path).expanduser(),
            summary=summary_text,
            estimate=Estimate(optimistic=optimistic, likely=likely, pessimistic=pessimistic),
            rationale=rationale,
            work_slices=work_slices,
        )

    @server.tool()
    def add_slice(effort: str, title: str) -> Acknowledgement:
        """Add a slice. One added while the effort is active is scope growth."""
        return recorder.add_slice(effort, title)

    @server.tool()
    def close_slice(effort: str, work_slice: str, pull_request: str) -> Acknowledgement:
        """Close a slice against its pull request."""
        return recorder.close_slice(effort, work_slice, pull_request)

    @server.tool()
    def drop_slice(effort: str, work_slice: str, reason: str) -> Acknowledgement:
        """Drop a slice that turned out to be unnecessary."""
        return recorder.drop_slice(effort, work_slice, reason)

    @server.tool()
    def rename_slice(effort: str, work_slice: str, title: str) -> Acknowledgement:
        """Rename a slice."""
        return recorder.rename_slice(effort, work_slice, title)

    @server.tool()
    def clock_in(
        effort: str,
        work_slice: str | None = None,
        kind: IntervalKind = IntervalKind.WORK,
        internal: int = 0,
        external: int = 0,
        participants: list[str] | None = None,
        note: str | None = None,
    ) -> Acknowledgement:
        """Start an interval. Refused if one is already open."""
        meeting = None
        if kind is IntervalKind.MEETING:
            meeting = MeetingParticipants(
                internal=internal, external=external, names=participants or []
            )
        return recorder.clock_in(effort, work_slice, kind, meeting, note)

    @server.tool()
    def clock_out(at: str | None = None, note: str | None = None) -> Acknowledgement:
        """Close the open interval."""
        return recorder.clock_out(datetime.fromisoformat(at) if at else None, note)

    @server.tool()
    def annotate_interval(
        effort: str,
        interval: str,
        internal: int = 0,
        external: int = 0,
        participants: list[str] | None = None,
        note: str | None = None,
    ) -> Acknowledgement:
        """Attach meeting participants or a note to an interval after the fact."""
        meeting = MeetingParticipants(
            internal=internal, external=external, names=participants or []
        )
        return recorder.annotate_interval(effort, interval, meeting, note)

    @server.tool()
    def repair_interval(
        effort: str, interval: str, start: str | None = None, stop: str | None = None
    ) -> Acknowledgement:
        """Correct an interval's bounds. Appends; never rewrites."""
        return recorder.repair_interval(
            effort,
            interval,
            datetime.fromisoformat(start) if start else None,
            datetime.fromisoformat(stop) if stop else None,
        )

    @server.tool()
    def record_absence(
        start: str, stop: str, kind: AbsenceKind, note: str | None = None
    ) -> Acknowledgement:
        """Declare time not spent working. Retroactive by design."""
        return recorder.record_absence(
            datetime.fromisoformat(start), datetime.fromisoformat(stop), kind, note
        )

    @server.tool()
    def record_revision(
        effort: str, optimistic: float, likely: float, pessimistic: float, rationale: str
    ) -> Acknowledgement:
        """Record a revised estimate, typically when a slice is inserted."""
        return recorder.record_revision(
            effort,
            Estimate(optimistic=optimistic, likely=likely, pessimistic=pessimistic),
            rationale,
        )

    @server.tool()
    def record_final_plan(
        effort: str,
        plan_path: str,
        summary_text: str,
        optimistic: float,
        likely: float,
        pessimistic: float,
        rationale: str,
    ) -> Acknowledgement:
        """Record the final plan and the counterfactual estimate against it."""
        return recorder.record_final_plan(
            effort,
            Path(plan_path).expanduser(),
            summary_text,
            Estimate(optimistic=optimistic, likely=likely, pessimistic=pessimistic),
            rationale,
        )

    @server.tool()
    def harvest_commits(
        effort: str, work_slice: str | None, path: str, since: str, until: str
    ) -> Acknowledgement:
        """Copy commit metadata from a working tree into the store."""
        return recorder.harvest_commits(
            effort,
            work_slice,
            Path(path).expanduser(),
            datetime.fromisoformat(since),
            datetime.fromisoformat(until),
        )

    @server.tool()
    def record_landed_commit(
        effort: str, work_slice: str | None, repository: str, identifier: str
    ) -> Acknowledgement:
        """Record the durable commit that landed on the default branch."""
        return recorder.record_landed_commit(effort, work_slice, repository, identifier)

    @server.tool()
    def remap_commits(effort: str, old: str, new: str, reason: str) -> Acknowledgement:
        """Map a rewritten commit id onto its replacement."""
        return recorder.remap_commits(effort, old, new, reason)

    @server.tool()
    def finish_effort(effort: str) -> Acknowledgement:
        """Mark an effort done."""
        return recorder.finish_effort(effort)

    # These five tools are registered under a name that collides with a
    # module-level function imported above (`reference_efforts`, `current`,
    # `effort_table`, `effort_detail`, `summary`). Naming the local function
    # the same as the import would also shadow the import inside this
    # function's scope, breaking the call within the tool body — so each
    # local function keeps a distinct `_tool` name and the registration name
    # is set explicitly instead.

    @server.tool(name="reference_efforts")
    def reference_efforts_tool(limit: int = 10, kind: str | None = None) -> list[ReferenceEffort]:
        """Prior efforts with their summaries and estimates, for comparison. No actuals."""
        return reference_efforts(store, limit, kind)

    @server.tool(name="current")
    def current_tool() -> CurrentStatus:
        """What is clocked in, and since when."""
        return current(store)

    @server.tool(name="effort_table")
    def effort_table_tool() -> list[EffortRow]:
        """One near-raw row per effort: estimates, wall hours, slice counts."""
        return effort_table(store, config)

    @server.tool(name="effort_detail")
    def effort_detail_tool(effort: str) -> EffortDetail:
        """One effort's full event history."""
        return effort_detail(store, config, effort)

    @server.tool(name="summary")
    def summary_tool() -> Summary:
        """Aggregate calibration, or an honest refusal when there is too little data."""
        return summary(store, config)

    return server


def main() -> None:
    config = load_config(os.environ)
    store = Store(config.store_path)
    store.initialise()
    build_server(store, config).run()
