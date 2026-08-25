#!/usr/bin/env bash
# Report whether a timer is running, so a forgotten clock-in is visible
# at the only moment it is cheap to fix.
set -euo pipefail
estimate-maestro-cli current || true
