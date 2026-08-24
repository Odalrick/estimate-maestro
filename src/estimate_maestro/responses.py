from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from estimate_maestro.models import Estimate

FORBIDDEN_NAME_PARTS = (
    "hours",
    "minutes",
    "seconds",
    "duration",
    "elapsed",
    "total",
    "wall",
    "average",
    "median",
    "share",
)


class ToolCategory(StrEnum):
    RECORDING = "recording"
    ESTIMATION = "estimation"
    STATUS = "status"
    CALIBRATION = "calibration"


class Acknowledgement(BaseModel):
    recorded: str
    identifier: str


class ReferenceEffort(BaseModel):
    effort: str
    title: str
    kind: str
    summary: str
    initial: Estimate
    final: Estimate | None = None


class CurrentStatus(BaseModel):
    effort: str | None = None
    work_slice: str | None = None
    interval: str | None = None
    since: datetime | None = None


def tainted_field_names(model: type[BaseModel], prefix: str = "") -> list[str]:
    offenders: list[str] = []
    for name, field in model.model_fields.items():
        path = f"{prefix}{name}"
        if any(part in name.lower() for part in FORBIDDEN_NAME_PARTS):
            offenders.append(path)
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            offenders.extend(tainted_field_names(annotation, prefix=f"{path}."))
    return offenders
