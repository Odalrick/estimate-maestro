# estimate-maestro

A personal MCP server and command-line tool for recording estimates and wall
time, so that estimates can eventually be checked against outcomes instead of
against feeling.

**This is a data collection tool for estimation calibration, not an
estimator.** It never estimates anything for you. It records what you
estimated a piece of work at, what the plan turned out to be, and how much
wall time the work actually took. What you do with that record — comparing,
noticing drift, deciding you were consistently optimistic about a certain kind
of work — is up to you and to whatever reads the store later. The tool's job
stops at recording honestly.

## The model

Four kinds of thing get recorded:

- **Effort** — a piece of work worth tracking on its own: a pull request, a
  mega-PR, anything with a plan and a size. An effort exists from the moment
  it has a plan artefact (a spec, a `.PR.md`, whatever the plan lives in) and
  an initial estimate. Before that point there is nothing to record yet.
- **Slice** — a piece of an effort, usually a sub-PR. Slices are added, closed
  against a pull request, dropped, or renamed. A slice added before the effort
  starts is part of the original plan; one added afterwards is scope growth,
  and the two are kept distinguishable in the record.
- **Interval** — a clocked-in span of time, ordinarily against a slice.
  Intervals are closed manually, closed automatically when a session ends
  with the clock still running, or derived after the fact from commit
  timestamps when nothing was clocked in at all.
- **Absence** — time that was not worked at all: a holiday, an appointment,
  an unrelated meeting. Absences are recorded retroactively and are expected
  to be. They subtract from whatever interval they overlap.

## Estimates: three-point triples in story points

Every estimate is a **PERT triple** — optimistic, likely, pessimistic — given
in an abstract points scale, never in hours. The expected value and the
standard deviation are derived from the triple on read; nothing stores a
single "the estimate is N" number, because a bare number throws away the
uncertainty that made it an estimate rather than a fact.

Points are anchored by comparing the work at hand to prior efforts of similar
shape, not by converting a felt number of hours into points in your head. The
whole point of an abstract scale is to compare like with like across efforts
whose actual duration you don't yet know.

An effort is estimated **twice**:

- The **initial** estimate, made against the plan as first written, at the
  same slice count the plan started with.
- The **final** estimate, made at the retrospective against the plan as it
  actually turned out — including every slice inserted along the way. This is
  a **counterfactual**: "given everything you now know about how this
  actually shook out, what would you have estimated?" — never "how long did
  it take?", and never a measurement of anything.

Splitting the estimate into two passes is what makes the two ways an estimate
can go wrong separable after the fact. The initial pass can be wrong because
of **inventory error** — work existed that nobody knew about yet, or work
that was assumed to exist turned out not to. The final pass, made against the
plan as it actually turned out, isolates **sizing error** — the items that
were known about all along and simply judged wrongly. A single number per
effort conflates the two; two numbers, one per pass, keep them apart.

A revised estimate can also be recorded mid-effort — typically when a slice is
inserted that was not in the original plan — without waiting for the
retrospective.

## The time model: a normal day is assumed

**A normal working day is assumed by default, and only deviations from it are
recorded.** Clocking in and out is the exception, not the routine — the tool
does not expect a stopwatch running for eight hours every day. Concretely:

- **Manually clocked time counts in full**, whatever hours it falls in.
  Evenings and weekends included: if you clocked in at 22:00 on a Saturday,
  that is real time and it is recorded as such, with no working-hours
  adjustment applied to it.
- **The working-hours model only ever applies where no time was actually
  recorded.** There are exactly two places it is used:
  - **Clamping a forgotten timer.** If a session ends with the clock still
    running, the interval is closed at the configured end of the working day
    (or, outside the configured working days and hours, capped at a fixed
    session length) rather than staying open indefinitely or being guessed at
    to the minute.
  - **Reconstructing intervals from commit timestamps** when nothing was ever
    clocked in for a slice. A cluster of nearby commits becomes a derived
    working session, using the working-hours model to decide how much of the
    span between them counts as work rather than an overnight gap.

An absence recorded over a span subtracts from any interval — clocked or
derived — that it overlaps, in full for a manually clocked interval and
through the working-hours model for a derived one.

## Tool categories and the taint rule

Every tool the MCP server exposes falls into exactly one category:

- **recording** — `start_effort`, `add_slice`, `close_slice`, `drop_slice`,
  `rename_slice`, `clock_in`, `clock_out`, `annotate_interval`,
  `repair_interval`, `record_absence`, `record_revision`,
  `record_final_plan`, `harvest_commits`, `record_landed_commit`,
  `remap_commits`, `finish_effort`.
- **estimation** — `reference_efforts`, which shows prior efforts for
  comparison while an estimate is being made.
- **status** — `current`, which reports what is clocked in and since when.
- **calibration** — `effort_table`, `effort_detail`, `summary`, which read
  the accumulated record back out.

**Recording, estimation and status tools never return a duration or an
aggregate. Only calibration tools may.** This is enforced structurally: every
response model used by a recording, estimation or status tool is checked for
field names containing words like `hours`, `minutes`, `duration`, `wall`,
`average`, or `share`, and the check fails if one is found.

The reason is not tidiness. An estimate made after seeing the real duration of
the work is an anchored echo of that duration, not an independent judgement —
the number you'd produce is contaminated by having just seen the answer. The
taint rule keeps a wall-time figure from ever surfacing in a tool response
while an estimate is being made or a clock is being run, so that the
initial-versus-final comparison stays honest. Calibration tools are exempt
because their entire purpose is to report exactly those figures, once the
estimating is done.

## Environment variables

All are optional; every one has a default. Read from
`src/estimate_maestro/config.py`, not from this list, if the two ever
disagree.

| Variable                                          | Default                        | Meaning                                                                 |
|----------------------------------------------------|---------------------------------|--------------------------------------------------------------------------|
| `ESTIMATE_MAESTRO_STORE`                            | `~/mcp/estimate-maestro-store`  | Path to the store directory.                                            |
| `ESTIMATE_MAESTRO_DAY_START`                        | `09:00`                         | Start of the working day (ISO 8601 time).                               |
| `ESTIMATE_MAESTRO_DAY_END`                          | `17:00`                         | End of the working day (ISO 8601 time).                                 |
| `ESTIMATE_MAESTRO_LUNCH_START`                      | `12:00`                         | Start of the daily lunch break, excluded from working seconds.          |
| `ESTIMATE_MAESTRO_LUNCH_END`                        | `13:00`                         | End of the daily lunch break.                                            |
| `ESTIMATE_MAESTRO_WORKDAYS`                         | `0,1,2,3,4`                     | Comma-separated weekdays counted as working days (Monday `0` … Sunday `6`). |
| `ESTIMATE_MAESTRO_OFF_HOURS_SESSION_CAP_MINUTES`    | `240` (4 hours)                 | Maximum length given to a clamped session that starts outside the working-hours window. |
| `ESTIMATE_MAESTRO_DERIVE_LEAD_IN_MINUTES`           | `30`                             | Time added before the earliest commit in a derived session, to cover work done before the first commit. |
| `ESTIMATE_MAESTRO_DERIVE_SESSION_GAP_MINUTES`       | `120` (2 hours)                 | Working-time gap between commits beyond which a derived session is considered to have ended and a new one begun. |
| `ESTIMATE_MAESTRO_MINIMUM_EFFORTS`                  | `5`                              | Minimum number of recorded efforts before `summary` reports figures rather than an honest refusal. |

`ESTIMATE_MAESTRO_DERIVE_LEAD_IN_MINUTES` must not exceed
`ESTIMATE_MAESTRO_DERIVE_SESSION_GAP_MINUTES`; the server refuses to start
otherwise.

## The command-line tool

`estimate-maestro-cli` covers the everyday recording actions that do not need
a conversation: `clock-in`, `clock-out`, `current`, `record-absence`,
`effort-table`, and `summary`. Actions that only make sense as part of an
estimating conversation — starting an effort, revising an estimate, recording
the final plan, harvesting commits — are MCP tools only, not CLI commands, on
purpose: they are meant to happen inside a session that shows comparable prior
efforts, not as a bare command typed without that context.

### Exit codes

| Code | Meaning                                                                 |
|------|--------------------------------------------------------------------------|
| `0`  | Success.                                                                 |
| `1`  | An error occurred.                                                       |
| `3`  | `clock-out` only: nothing was clocked in. Expected and frequent, not a failure — a script wiring `clock-out` into an automatic hook should treat `3` the same as `0`. |

## Installation

None of the following has been run for you — copy the commands below and run
them yourself.

Register the MCP server:

```sh
claude mcp add --scope user maestro-estimate -- uv --directory ~/mcp/estimate-maestro run estimate-maestro
```

Symlink the two skills into your personal skills directory:

```sh
ln -s ~/mcp/estimate-maestro/skills/recording-work-time ~/.claude/skills/recording-work-time
ln -s ~/mcp/estimate-maestro/skills/estimating-work ~/.claude/skills/estimating-work
```

Make the store a git repository. Its files are plain text and append-only so
that it can be committed and roam between machines, and it is the only
surviving copy of what it records: a number lost or wrong in there cannot be
reconstructed from anywhere else. Keep it **private** — it holds project names,
branch names and how long things took, none of which belong in a public repo.

```sh
mkdir -p ~/mcp/estimate-maestro-store
git -C ~/mcp/estimate-maestro-store init
```

Point the server and CLI at your store — add this to whatever environment
Claude Code and your shell both see (for example your shell profile, and the
environment passed to the MCP registration above):

```sh
export ESTIMATE_MAESTRO_STORE=~/mcp/estimate-maestro-store
```

Wire the two hook scripts into `~/.claude/settings.json`: `hooks/session-end.sh`
as a `SessionEnd` hook (closes a forgotten timer, clamped to the configured
working day) and `hooks/session-start.sh` as a `SessionStart` hook (reports
whether a timer is already running):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "~/mcp/estimate-maestro/hooks/session-start.sh" }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          { "type": "command", "command": "~/mcp/estimate-maestro/hooks/session-end.sh" }
        ]
      }
    ]
  }
}
```

Merge that into the existing `hooks` block in `~/.claude/settings.json` rather
than overwriting it, if one is already there.

## Development

```sh
uv sync --locked
uv run ruff format --check
uv run ruff check
uv run pyright
uv run pytest src/ -v
```
