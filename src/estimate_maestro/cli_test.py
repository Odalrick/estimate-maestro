from datetime import datetime
from pathlib import Path

import pytest

from estimate_maestro.cli import run
from estimate_maestro.clock import clamp_stop
from estimate_maestro.config import load_config
from estimate_maestro.errors import AlreadyClockedIn, NotClockedIn, UnknownSlice
from estimate_maestro.store import INTERVALS_LOG, SLICES_LOG, Store

FORBIDDEN_WORDS = (
    "hour",
    "minute",
    "second",
    "duration",
    "elapsed",
    "total",
    "wall",
    "average",
    "median",
    "share",
)


def assert_no_forbidden_words(text: str) -> None:
    lowered = text.lower()
    for word in FORBIDDEN_WORDS:
        assert word not in lowered, f"forbidden word {word!r} leaked in: {text!r}"


@pytest.fixture
def environment(tmp_path: Path) -> dict[str, str]:
    return {"ESTIMATE_MAESTRO_STORE": str(tmp_path / "store")}


@pytest.fixture
def store(environment: dict[str, str]) -> Store:
    created = Store(Path(environment["ESTIMATE_MAESTRO_STORE"]))
    created.initialise()
    created.create_effort(
        "2026-08-24-thing",
        {
            "title": "Thing",
            "kind": "other",
            "status": "active",
            "created_at": "2026-08-24T09:00:00+00:00",
            "repositories": [],
            "pull_requests": [],
        },
    )
    return created


def test_current_reports_nothing_when_no_timer_runs(store, environment, capsys):
    code = run(["current"], environment)

    assert code == 0
    assert capsys.readouterr().out == "Nothing clocked in.\n"


def test_clock_in_prints_an_acknowledgement_and_leaks_no_duration_words(store, environment, capsys):
    code = run(["clock-in", "2026-08-24-thing"], environment)

    output = capsys.readouterr().out
    assert code == 0
    assert output.startswith("Ok, recorded — interval iv-")
    assert output.endswith(".\n")
    assert_no_forbidden_words(output)


def test_clock_in_then_current_reports_the_effort(store, environment, capsys):
    run(["clock-in", "2026-08-24-thing"], environment)
    capsys.readouterr()

    code = run(["current"], environment)

    opened = store.read("2026-08-24-thing", INTERVALS_LOG)[-1]
    since = datetime.fromisoformat(opened["at"])
    output = capsys.readouterr().out
    assert code == 0
    assert output == f"2026-08-24-thing (no slice) open since {since}.\n"
    assert_no_forbidden_words(output)


def test_clock_in_with_a_slice_reports_the_slice_in_current(store, environment, capsys):
    store.append(
        "2026-08-24-thing",
        SLICES_LOG,
        {"event": "added", "slice": "sl-01", "title": "First slice", "phase": "in_flight"},
    )

    run(["clock-in", "2026-08-24-thing", "--slice", "sl-01"], environment)
    capsys.readouterr()
    run(["current"], environment)

    output = capsys.readouterr().out
    assert output.startswith("2026-08-24-thing (sl-01) open since ")


def test_clock_in_against_an_unknown_slice_exits_non_zero_with_the_library_error(
    store, environment, capsys
):
    code = run(["clock-in", "2026-08-24-thing", "--slice", "sl-99"], environment)

    assert code == 1
    assert capsys.readouterr().err == f"{UnknownSlice('sl-99')}\n"


def test_clock_in_while_already_clocked_in_exits_non_zero(store, environment, capsys):
    run(["clock-in", "2026-08-24-thing"], environment)
    capsys.readouterr()

    code = run(["clock-in", "2026-08-24-thing"], environment)

    assert code == 1
    assert (
        capsys.readouterr().err
        == f"{AlreadyClockedIn('an interval is already open; clock out first')}\n"
    )


def test_clock_out_records_manual_provenance_by_default(store, environment, capsys):
    run(["clock-in", "2026-08-24-thing"], environment)
    capsys.readouterr()

    code = run(["clock-out"], environment)

    closed = store.read("2026-08-24-thing", INTERVALS_LOG)[-1]
    output = capsys.readouterr().out
    assert code == 0
    assert closed["event"] == "clock_out"
    assert closed["provenance"] == "manual"
    assert output.startswith(f"Ok, recorded — interval {closed['interval']}")
    assert_no_forbidden_words(output)


def test_clock_out_with_at_uses_the_given_timestamp(store, environment, capsys):
    run(["clock-in", "2026-08-24-thing"], environment)
    capsys.readouterr()

    run(["clock-out", "--at", "2026-08-24T15:30:00+00:00"], environment)

    closed = store.read("2026-08-24-thing", INTERVALS_LOG)[-1]
    assert closed["at"] == "2026-08-24T15:30:00+00:00"
    assert closed["provenance"] == "manual"


def test_clock_out_at_last_activity_clamps_and_records_provenance(store, environment):
    run(["clock-in", "2026-08-24-thing"], environment)

    run(["clock-out", "--at-last-activity", "2026-09-30T12:00:00+00:00"], environment)

    opened = store.read("2026-08-24-thing", INTERVALS_LOG)[0]
    closed = store.read("2026-08-24-thing", INTERVALS_LOG)[-1]
    expected_stop = clamp_stop(
        datetime.fromisoformat(opened["at"]),
        datetime.fromisoformat("2026-09-30T12:00:00+00:00"),
        load_config(environment),
    )

    assert closed["event"] == "clock_out"
    assert closed["provenance"] == "clamped"
    assert closed["at"] == expected_stop.isoformat()


def test_clock_out_without_a_timer_exits_with_the_dedicated_code(store, environment, capsys):
    code = run(["clock-out"], environment)

    assert code == 3
    assert capsys.readouterr().err == f"{NotClockedIn('no interval is open')}\n"


def test_clock_out_with_a_malformed_at_exits_one_naming_the_argument(store, environment, capsys):
    run(["clock-in", "2026-08-24-thing"], environment)
    capsys.readouterr()

    code = run(["clock-out", "--at", "not-a-timestamp"], environment)

    error = capsys.readouterr().err
    assert code == 1
    assert error == "--at is not a valid ISO 8601 timestamp: 'not-a-timestamp'\n"
    assert "Traceback" not in error


def test_clock_out_with_a_malformed_at_last_activity_exits_one_naming_the_argument(
    store, environment, capsys
):
    run(["clock-in", "2026-08-24-thing"], environment)
    capsys.readouterr()

    code = run(["clock-out", "--at-last-activity", "2026-13-40"], environment)

    error = capsys.readouterr().err
    assert code == 1
    assert error == "--at-last-activity is not a valid ISO 8601 timestamp: '2026-13-40'\n"
    assert "Traceback" not in error


def test_a_genuine_clock_out_error_still_exits_one_not_three(store, environment, capsys):
    # clock_out_clamped still needs an open interval; with none open it raises
    # NotClockedIn same as plain clock-out, but a malformed argument is a
    # different, genuine error and must not be confused with "nothing to do".
    code = run(["clock-out", "--at", "not-a-timestamp"], environment)

    assert code == 1
    assert capsys.readouterr().err == "--at is not a valid ISO 8601 timestamp: 'not-a-timestamp'\n"


def test_record_absence_prints_an_acknowledgement_and_stores_it(store, environment, capsys):
    code = run(
        [
            "record-absence",
            "2026-08-25T00:00:00+00:00",
            "2026-08-26T00:00:00+00:00",
            "vacation",
            "--note",
            "long weekend",
        ],
        environment,
    )

    absences = store.read_absences()
    output = capsys.readouterr().out
    assert code == 0
    assert len(absences) == 1
    assert absences[0]["kind"] == "vacation"
    assert absences[0]["note"] == "long weekend"
    assert output.startswith(f"Ok, recorded — absence {absences[0]['identifier']}")
    assert_no_forbidden_words(output)


def test_record_absence_rejects_an_unknown_kind(store, environment):
    with pytest.raises(SystemExit):
        run(
            ["record-absence", "2026-08-25T00:00:00+00:00", "2026-08-26T00:00:00+00:00", "made-up"],
            environment,
        )

    assert store.read_absences() == []


def test_effort_table_reports_the_effort_as_json(store, environment, capsys):
    code = run(["effort-table"], environment)

    output = capsys.readouterr().out
    assert code == 0
    assert '"effort": "2026-08-24-thing"' in output
    assert '"wall_hours"' in output


def test_summary_reports_the_refusal_note_below_the_minimum(store, environment, capsys):
    code = run(["summary"], environment)

    output = capsys.readouterr().out
    assert code == 0
    assert '"efforts_counted": 1' in output
    assert '"mean_hours_per_point": null' in output
    assert "calibration is not established" in output


def test_a_corrupted_stored_interval_raises_instead_of_being_swallowed(store, environment):
    # A malformed CLI argument (MalformedArgument) and a corrupted stored
    # timestamp read back by library internals must not look the same. The
    # former is an ordinary typo and exits 1 with a clean message; the latter
    # is a genuine bug and must propagate as an uncaught ValueError, not be
    # reported as if it were user error.
    store.append(
        "2026-08-24-thing",
        INTERVALS_LOG,
        {
            "event": "clock_in",
            "interval": "iv-corrupt",
            "slice": None,
            "kind": "work",
            "at": "CORRUPTED-NOT-A-DATE",
        },
    )

    with pytest.raises(ValueError, match="CORRUPTED-NOT-A-DATE"):
        run(["clock-out", "--at-last-activity", "2026-09-30T12:00:00+00:00"], environment)


def test_a_malformed_config_variable_exits_one_with_a_clean_message(store, environment, capsys):
    broken_environment = {**environment, "ESTIMATE_MAESTRO_DAY_START": "not-a-time"}

    code = run(["current"], broken_environment)

    error = capsys.readouterr().err
    assert code == 1
    assert error == "ESTIMATE_MAESTRO_DAY_START is not an ISO 8601 time: 'not-a-time'\n"
    assert "Traceback" not in error
