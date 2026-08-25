import argparse
import json
import os
import sys
from collections.abc import Mapping
from datetime import datetime

from estimate_maestro.calibration import effort_table, summary
from estimate_maestro.config import load_config
from estimate_maestro.errors import (
    EstimateMaestroError,
    InvalidConfiguration,
    MalformedArgument,
    NotClockedIn,
)
from estimate_maestro.models import AbsenceKind
from estimate_maestro.recording import Recorder
from estimate_maestro.status import current
from estimate_maestro.store import Store

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOTHING_CLOCKED_IN = 3

EXIT_CODES_EPILOG = (
    "exit codes:\n"
    f"  {EXIT_OK}  success\n"
    f"  {EXIT_ERROR}  an error occurred\n"
    f"  {EXIT_NOTHING_CLOCKED_IN}  clock-out only: nothing was clocked in (not a failure)\n"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="estimate-maestro-cli",
        epilog=EXIT_CODES_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    clock_in = subparsers.add_parser("clock-in")
    clock_in.add_argument("effort")
    clock_in.add_argument("--slice", dest="work_slice", default=None)
    clock_in.add_argument("--note", default=None)

    clock_out = subparsers.add_parser("clock-out")
    clock_out.add_argument("--at", default=None)
    clock_out.add_argument("--at-last-activity", dest="last_activity", default=None)

    subparsers.add_parser("current")
    subparsers.add_parser("effort-table")
    subparsers.add_parser("summary")

    absence = subparsers.add_parser("record-absence")
    absence.add_argument("start")
    absence.add_argument("stop")
    absence.add_argument("kind", choices=[kind.value for kind in AbsenceKind])
    absence.add_argument("--note", default=None)

    return parser


def _parse_timestamp(argument: str, value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise MalformedArgument(argument, value) from error


def run(arguments: list[str], environment: Mapping[str, str]) -> int:
    parsed = _parser().parse_args(arguments)

    try:
        try:
            config = load_config(environment)
        except ValueError as error:
            raise InvalidConfiguration(str(error)) from error
        store = Store(config.store_path)
        store.initialise()
        recorder = Recorder(store=store, config=config)

        if parsed.command == "clock-in":
            acknowledgement = recorder.clock_in(
                parsed.effort, work_slice=parsed.work_slice, note=parsed.note
            )
            print(f"Ok, recorded — interval {acknowledgement.identifier}.")
        elif parsed.command == "clock-out":
            if parsed.last_activity is not None:
                acknowledgement = recorder.clock_out_clamped(
                    _parse_timestamp("--at-last-activity", parsed.last_activity)
                )
            else:
                acknowledgement = recorder.clock_out(
                    _parse_timestamp("--at", parsed.at) if parsed.at else None
                )
            print(f"Ok, recorded — interval {acknowledgement.identifier}.")
        elif parsed.command == "current":
            reported = current(store)
            if reported.interval is None:
                print("Nothing clocked in.")
            else:
                work_slice = reported.work_slice if reported.work_slice is not None else "no slice"
                print(f"{reported.effort} ({work_slice}) open since {reported.since}.")
        elif parsed.command == "record-absence":
            acknowledgement = recorder.record_absence(
                _parse_timestamp("start", parsed.start),
                _parse_timestamp("stop", parsed.stop),
                AbsenceKind(parsed.kind),
                parsed.note,
            )
            print(f"Ok, recorded — absence {acknowledgement.identifier}.")
        elif parsed.command == "effort-table":
            print(
                json.dumps(
                    [row.model_dump(mode="json") for row in effort_table(store, config)], indent=2
                )
            )
        elif parsed.command == "summary":
            print(json.dumps(summary(store, config).model_dump(mode="json"), indent=2))
    except NotClockedIn as error:
        print(str(error), file=sys.stderr)
        return EXIT_NOTHING_CLOCKED_IN
    except EstimateMaestroError as error:
        print(str(error), file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


def main() -> None:
    raise SystemExit(run(sys.argv[1:], os.environ))
