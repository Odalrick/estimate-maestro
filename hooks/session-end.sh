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
# The command's own stderr is discarded (2>/dev/null): its "no interval is
# open" message is the exit-3 case's own error text, and printing it here on
# every quiet day is exactly the noise this exit-code split exists to avoid.
# A genuine failure is still reported below, from the exit code alone, which
# survives the stderr redirect untouched.
set -uo pipefail
estimate-maestro-cli clock-out --at-last-activity "$(date --iso-8601=seconds)" 2>/dev/null
status=$?
if [ "$status" -ne 0 ] && [ "$status" -ne 3 ]; then
    echo "session-end.sh: clock-out failed (exit $status)" >&2
fi
