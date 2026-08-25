#!/usr/bin/env bash
# Close any interval left running, clamped to the configured quit time.
# Wire into Claude Code settings.json as a SessionEnd hook.
#
# Exit codes from estimate-maestro-cli clock-out:
#   0 - clocked out successfully
#   1 - a real error
#   3 - nothing was clocked in (expected, frequent, not a failure)
#
# set -e is deliberately omitted: with it the script would exit at the
# failing command before reaching the status check below.
#
# The command's combined output is captured rather than discarded, so a
# genuine failure (exit 1, or exit 127 if the CLI is missing entirely) can be
# reported with its actual message, not just a bare exit code. On the two
# expected paths (0: clocked out; 3: nothing was open) nothing is printed at
# all — a normal day, forgotten clock-in included, stays silent.
set -uo pipefail
output=$(estimate-maestro-cli clock-out --at-last-activity "$(date --iso-8601=seconds)" 2>&1)
status=$?
if [ "$status" -ne 0 ] && [ "$status" -ne 3 ]; then
    echo "session-end.sh: clock-out failed (exit $status): $output" >&2
fi
