from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Scale(StrEnum):
    POINTS = "points"


class EstimatePass(StrEnum):
    INITIAL = "initial"
    REVISION = "revision"
    FINAL = "final"


class EffortKind(StrEnum):
    MEGA_PULL_REQUEST = "mega-pull-request"
    STANDALONE_PULL_REQUEST = "standalone-pull-request"
    OTHER = "other"


class EffortStatus(StrEnum):
    PLANNING = "planning"
    ACTIVE = "active"
    DONE = "done"
    ABANDONED = "abandoned"


class IntervalKind(StrEnum):
    WORK = "work"
    MEETING = "meeting"


class IntervalEvent(StrEnum):
    CLOCK_IN = "clock_in"
    CLOCK_OUT = "clock_out"
    ANNOTATE = "annotate"


class Provenance(StrEnum):
    MANUAL = "manual"
    CLAMPED = "clamped"
    DERIVED_FROM_COMMITS = "derived_from_commits"
    REPAIRED = "repaired"


class AbsenceKind(StrEnum):
    VACATION = "vacation"
    APPOINTMENT = "appointment"
    UNRELATED_MEETING = "unrelated_meeting"
    OTHER = "other"


class SliceEvent(StrEnum):
    ADDED = "added"
    CLOSED = "closed"
    DROPPED = "dropped"
    RENAMED = "renamed"


class Vcs(StrEnum):
    GIT = "git"
    FOSSIL = "fossil"
    OTHER = "other"


class Estimate(BaseModel):
    scale: Scale = Scale.POINTS
    optimistic: float
    likely: float
    pessimistic: float

    @model_validator(mode="after")
    def _check_ordering(self) -> "Estimate":  # noqa: UP037
        if not self.optimistic <= self.likely <= self.pessimistic:
            raise ValueError("expected optimistic <= likely <= pessimistic")
        return self

    @property
    def expected(self) -> float:
        return (self.optimistic + 4 * self.likely + self.pessimistic) / 6

    @property
    def standard_deviation(self) -> float:
        return (self.pessimistic - self.optimistic) / 6


class MeetingParticipants(BaseModel):
    internal: int = Field(ge=0)
    external: int = Field(ge=0)
    names: list[str] = Field(default_factory=list)
