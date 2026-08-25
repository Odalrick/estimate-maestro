#!/usr/bin/env bash
# Close any interval left running, clamped to the configured quit time.
# Wire into Claude Code settings.json as a SessionEnd hook.
set -euo pipefail
estimate-maestro-cli clock-out --at-last-activity "$(date --iso-8601=seconds)" 2>/dev/null || true
