from datetime import time, timedelta
from pathlib import Path

from estimate_maestro.config import load_config


def test_defaults_apply_when_environment_is_empty():
    config = load_config({})

    assert config.working_hours.day_start == time(9, 0)
    assert config.working_hours.day_end == time(17, 0)
    assert config.working_hours.lunch_start == time(12, 0)
    assert config.working_hours.lunch_end == time(13, 0)
    assert config.working_hours.workdays == frozenset({0, 1, 2, 3, 4})
    assert config.off_hours_session_cap == timedelta(hours=4)
    assert config.derive_lead_in == timedelta(minutes=30)
    assert config.derive_session_gap == timedelta(hours=2)
    assert config.minimum_efforts_for_analysis == 5


def test_the_store_defaults_to_the_xdg_data_directory():
    config = load_config({})

    assert config.store_path == Path.home() / ".local" / "share" / "estimate-maestro"


def test_the_store_default_honours_xdg_data_home():
    config = load_config({"XDG_DATA_HOME": "/somewhere/data"})

    assert config.store_path == Path("/somewhere/data/estimate-maestro")


def test_an_explicit_store_path_beats_xdg_data_home():
    config = load_config(
        {"XDG_DATA_HOME": "/somewhere/data", "ESTIMATE_MAESTRO_STORE": "~/chosen/store"}
    )

    assert config.store_path == Path.home() / "chosen" / "store"


def test_store_path_expands_a_leading_tilde():
    config = load_config({"ESTIMATE_MAESTRO_STORE": "~/somewhere/store"})

    assert config.store_path == Path.home() / "somewhere" / "store"
    assert "~" not in str(config.store_path)


def test_working_hours_are_overridable():
    config = load_config(
        {
            "ESTIMATE_MAESTRO_DAY_START": "08:30",
            "ESTIMATE_MAESTRO_DAY_END": "16:00",
            "ESTIMATE_MAESTRO_WORKDAYS": "0,1,2,3,4,5",
        }
    )

    assert config.working_hours.day_start == time(8, 30)
    assert config.working_hours.day_end == time(16, 0)
    assert config.working_hours.workdays == frozenset({0, 1, 2, 3, 4, 5})


def test_a_malformed_time_is_rejected_with_the_variable_named():
    try:
        load_config({"ESTIMATE_MAESTRO_DAY_START": "half past eight"})
    except ValueError as error:
        assert "ESTIMATE_MAESTRO_DAY_START" in str(error)
    else:
        raise AssertionError("expected a ValueError")


def test_a_lead_in_longer_than_the_session_gap_is_rejected_naming_both_variables():
    try:
        load_config(
            {
                "ESTIMATE_MAESTRO_DERIVE_LEAD_IN_MINUTES": "180",
                "ESTIMATE_MAESTRO_DERIVE_SESSION_GAP_MINUTES": "120",
            }
        )
    except ValueError as error:
        assert "ESTIMATE_MAESTRO_DERIVE_LEAD_IN_MINUTES" in str(error)
        assert "ESTIMATE_MAESTRO_DERIVE_SESSION_GAP_MINUTES" in str(error)
    else:
        raise AssertionError("expected a ValueError")
