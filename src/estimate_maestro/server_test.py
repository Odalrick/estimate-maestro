import asyncio
from pathlib import Path

import pytest

from estimate_maestro.config import load_config
from estimate_maestro.responses import ToolCategory, tainted_field_names
from estimate_maestro.server import TOOL_CATEGORIES, TOOL_RESPONSES, build_server
from estimate_maestro.store import Store


@pytest.fixture
def server(tmp_path: Path):
    store = Store(tmp_path / "store")
    store.initialise()
    return build_server(store, load_config({"ESTIMATE_MAESTRO_STORE": str(tmp_path / "store")}))


def registered_names(server) -> set[str]:
    return {tool.name for tool in asyncio.run(server.list_tools())}


def test_every_registered_tool_declares_a_category(server):
    assert registered_names(server) == set(TOOL_CATEGORIES)


def test_every_categorised_tool_declares_a_response_model():
    assert set(TOOL_CATEGORIES) == set(TOOL_RESPONSES)


def test_no_untainted_category_leaks_a_duration_or_aggregate():
    offenders = {
        name: tainted_field_names(TOOL_RESPONSES[name])
        for name, category in TOOL_CATEGORIES.items()
        if category is not ToolCategory.CALIBRATION
    }

    assert {name: found for name, found in offenders.items() if found} == {}


def test_the_recording_surface_answers_with_acknowledgements_only():
    from estimate_maestro.responses import Acknowledgement

    recording = [
        name for name, category in TOOL_CATEGORIES.items() if category is ToolCategory.RECORDING
    ]

    assert recording
    assert all(TOOL_RESPONSES[name] is Acknowledgement for name in recording)


def test_the_calibration_surface_is_the_only_one_permitted_aggregates():
    from estimate_maestro.calibration import Summary

    assert tainted_field_names(Summary) != []
    assert TOOL_CATEGORIES["summary"] is ToolCategory.CALIBRATION
