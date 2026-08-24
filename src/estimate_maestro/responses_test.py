from datetime import datetime
from typing import Any

import pytest
from pydantic import BaseModel

from estimate_maestro.responses import (
    Acknowledgement,
    CurrentStatus,
    ReferenceEffort,
    ToolCategory,
    tainted_field_names,
)

UNTAINTED_MODELS: list[type[BaseModel]] = [Acknowledgement, CurrentStatus, ReferenceEffort]


@pytest.mark.parametrize("model", UNTAINTED_MODELS)
def test_untainted_response_models_carry_no_duration_or_aggregate(model: type[BaseModel]):
    assert tainted_field_names(model) == []


def test_the_guard_catches_a_duration_field():
    class Tempting(BaseModel):
        wall_hours: float

    assert tainted_field_names(Tempting) == ["wall_hours"]


def test_the_guard_recurses_into_nested_models():
    class Inner(BaseModel):
        total_seconds: float

    class Outer(BaseModel):
        inner: Inner

    assert tainted_field_names(Outer) == ["inner.total_seconds"]


def test_current_status_reports_a_timestamp_and_not_an_elapsed():
    status = CurrentStatus(
        effort="2026-08-24-thing",
        work_slice="sl-01",
        interval="iv-0f3a",
        since=datetime.fromisoformat("2026-08-24T09:12:00+02:00"),
    )
    payload: dict[str, Any] = status.model_dump()

    assert "since" in payload
    assert not any("elapsed" in key for key in payload)


def test_the_four_categories_exist():
    assert {category.value for category in ToolCategory} == {
        "recording",
        "estimation",
        "status",
        "calibration",
    }
