from datetime import datetime
from enum import StrEnum
from typing import Any, get_args, get_origin

from pydantic import BaseModel

from estimate_maestro.models import Estimate

# Every word this project has actually used to name a measurement or an
# aggregate, not a generic list: the vocabulary has to cover the names the
# calibration models really carry, or the guard passes a model it should stop.
FORBIDDEN_NAME_PARTS = (
    "hours",
    "minutes",
    "seconds",
    "days",
    "duration",
    "elapsed",
    "total",
    "wall",
    "average",
    "mean",
    "median",
    "count",
    "rate",
    "growth",
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


def _nested_models(annotation: Any) -> list[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for argument in get_args(annotation):
        found.extend(_nested_models(argument))
    return found


def _hides_a_mapping(annotation: Any) -> bool:
    """Whether a mapping hides anywhere in this annotation.

    The guard reads field names, and a mapping has none — its keys are data. A
    response carrying one carries whatever the store put in it, wall-time
    figures included, so the field itself is the offender.
    """
    if annotation is dict or get_origin(annotation) is dict:
        return True
    return any(_hides_a_mapping(argument) for argument in get_args(annotation))


def tainted_field_names(model: type[BaseModel], prefix: str = "") -> list[str]:
    offenders: list[str] = []
    for name, field in model.model_fields.items():
        path = f"{prefix}{name}"
        if any(part in name.lower() for part in FORBIDDEN_NAME_PARTS) or _hides_a_mapping(
            field.annotation
        ):
            offenders.append(path)
        for nested_model in _nested_models(field.annotation):
            offenders.extend(tainted_field_names(nested_model, prefix=f"{path}."))
    return offenders
