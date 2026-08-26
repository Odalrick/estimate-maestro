# estimate-maestro

A personal MCP server and command-line tool for recording estimates and wall time, so that estimates can eventually be
checked against outcomes instead of against feeling.

Today it is a data collection tool for estimation calibration, not an estimator: it does not estimate anything for you.
It records what you estimated a piece of work at, what the plan turned out to be, and how much wall time the work
actually took. What you do with that record — comparing, noticing drift, deciding you were consistently optimistic about
a certain kind of work — is up to you and to whatever reads the store later. Through version 1.0.0 the tool's job stops
at recording honestly.

That is the scope of the first version, not the scope of the project. Helping you make your own estimates, and
eventually handing the estimating itself to an LLM or something like it, are both in scope later — and both need this
record to exist first.

## The model

Four kinds of thing get recorded:

- **Effort** — a piece of work that is supposed to be estimated: a pull request, a mega-PR, anything with a plan and an
  estimate. An effort exists from the moment it has a plan artefact (a spec, a `.PR.md`, whatever the plan lives in) and
  an initial estimate. Before that point there is nothing to record yet. The estimate excludes the time spent making the
  plan: recording starts once the plan exists, so counting the planning time in the estimate would skew the feedback.
- **Slice** — a piece of an effort, one step of the plan. Slices are added, closed against a pull request, dropped, or
  renamed. A slice added before the effort starts is part of the original plan; one added afterwards is scope growth,
  and the two are kept distinguishable in the record.
- **Interval** — a clocked-in span of time, ordinarily against a slice, or against the effort itself when there is
  nothing finer to clock against. Intervals are closed manually, closed automatically when a session ends with the
  clock still running, or derived after the fact from commit timestamps when nothing was clocked in at all.
- **Absence** — time that was not worked at all: a holiday, an appointment, an unrelated meeting. Absences can be
  recorded retroactively and are expected to be.

## The five things

Five pieces of data are what the tool exists to produce:

- the initial estimate;
- the initial plan;
- the final estimate;
- the final plan — the plan you actually executed;
- the total wall time taken, by the _one_ person working on the effort.

Everything else that gets recorded is in support of those five. The nature of the recording means other statistics
could be collected too, but they are by-products rather than the artefacts the tool is built to deliver.

This matters because the later work on helping with estimates will be built on those five things, and any system that
can provide them will serve equally well.

## Estimates: three-point triples in points

Every estimate is a **PERT triple** — optimistic, likely, pessimistic — given on an abstract points scale, never in
hours. The expected value and the standard deviation are derived from the triple on read; nothing stores a single "the
estimate is N" number, because a bare number throws away the uncertainty that made it an estimate rather than a fact.

Points are anchored by comparing the work at hand to prior efforts of similar shape, not by converting a felt number of
hours into points in your head. The whole point of an abstract scale is to compare like with like across efforts whose
actual duration you don't yet know.

Which scale is left entirely to you. Any numeric, roughly linear scale will do — this is a single-person tool, so the
points only ever have to mean something next to your own earlier estimates. Even consistency over time is a convenience
rather than a requirement: if you would size the same work at 50 points one year and 70 the next, the record still
tells you what you need to know.

Two estimates are what the tool actually uses:

- The **initial** estimate, made against the plan as first written, covering the slices the plan started with rather
  than the ones it grew.
- The **final** estimate, made at the retrospective against the plan as it actually turned out — including every slice
  inserted along the way. This is a **counterfactual**: "given everything you now know about how this actually shook
  out, what would you have estimated?" — never "how long did it take?", and never a measurement of anything.

Splitting the estimate into two passes is what makes the two ways an estimate can go wrong separable after the fact. The
initial pass can be wrong because of **inventory error** — work existed that nobody knew about yet, or work that was
assumed to exist turned out not to. The final pass, made against the plan as it actually turned out, isolates **sizing
error** — the items that were known about all along and simply judged wrongly. A single number per effort conflates the
two; two numbers, one per pass, keep them apart.

Revised estimates can also be recorded mid-effort — typically when a slice is inserted that was not in the original
plan — without waiting for the retrospective. Re-estimating as the plan grows is a healthy part of the process, so the
revisions are kept; but nothing reads them back yet, and only the initial and the final estimate feed the record. The
data is there in case a use for the middle turns up.

The final re-estimate has a second purpose: it trains the skill. Given what you now know, how should you estimate work
of this shape next time?

## The time model: a normal day is assumed

A normal working day is assumed by default. Clocking in and out is still the ordinary workflow, but a missed clock-out
should self-heal with reasonable accuracy rather than leaving a hole in the record.

The assumed day is 09:00–17:00, with one hour of lunch. That is under eight hours on purpose: the shortfall accounts for
meetings and other time not spent on the project.

- **Manually clocked time counts in full**, whatever hours it falls in. Evenings and weekends included: if you clocked
  in at 22:00 on a Saturday, that is what gets recorded, with no working-hours adjustment applied to it.
- **The working-hours model only ever applies where timestamps are missing.** There are exactly two places it is used:
  - **Ending a forgotten timer.** If a session ends with the clock still running, the interval is closed at the
    configured end of the day rather than staying open indefinitely.
  - **Reconstructing intervals from commit timestamps** when nothing was ever clocked in for a slice. A cluster of
    nearby commits becomes a derived working session, using the working-hours model to decide how much of the span
    between them counts as work rather than an overnight gap.

Every calendar day carries the same working hours; there is no concept of a non-working day. So the session started at
22:00 on the Saturday but never ended is considered ended at 17:00 on the Sunday. That is of course an unreasonable time
to record and unlikely to be accurate, but the simplicity makes the effects predictable, and it bounds the damage at
roughly a day: a session left running from 17:01 on a Friday closes at 17:00 on the Saturday, rather than accruing
credit all the way to Monday. The expectation is that the tooling "remembers" the clock-out for you, so the fallback is
rarely reached, and more reasonable times can usually be reconstructed from commit logs after the fact.

An absence recorded over a span subtracts from any interval — clocked or derived — that it overlaps: in full from a
manually clocked interval, and through the same reconstruction that produced a derived one.

## Tool categories and the taint rule

Every tool the MCP server exposes falls into exactly one category:

- **recording** — `start_effort`, `add_slice`, `close_slice`, `drop_slice`, `rename_slice`, `clock_in`, `clock_out`,
  `annotate_interval`, `repair_interval`, `record_absence`, `record_revision`, `record_final_plan`, `harvest_commits`,
  `record_landed_commit`, `remap_commits`, `finish_effort`.
- **status** — `current`, which reports what is clocked in and since when.
- **estimation** — `reference_efforts`, which shows the estimates recorded against prior efforts, for comparison while a
  new estimate is being made.
- **calibration** — `effort_table`, `effort_detail`, `summary`, which read the accumulated record back out.

**Recording, estimation and status tools never return a duration or an aggregate. Only calibration tools may.** This is
enforced structurally: every response model used by a recording, estimation or status tool is checked for field names
containing `hours`, `minutes`, `duration`, `wall`, `average`, or `share`, and the check fails if one is found.

The reason is narrower than it can look. An estimate made just after seeing the real duration of the work is an anchored
echo of that duration rather than an independent judgement; the concrete case to avoid is a final estimate landing on 10
because the clock-out just before it reported ten hours on the effort. So the rule keeps a wall-time figure from
surfacing in a tool response while an estimate is being made or a clock is being run. It is a guard against accidental
anchoring, not a claim that durations are dangerous — the estimation tools deliberately show prior estimates, which is
what makes an abstract scale usable at all. Calibration tools are exempt because reporting exactly those figures is
their entire purpose, once the estimating is done.

The estimation and calibration tools are very limited in the initial release. Usage will be needed to refine them into
worthwhile tools, but we have to start somewhere. They are a guess at what will be useful, and serve as validation that
everything needed is recorded.

## Environment variables

All are optional; every one has a default. Read from `src/estimate_maestro/config.py`, not from this list, if the two
ever disagree.

| Variable                       | Default                                                                              | Meaning                                                        |
|--------------------------------|--------------------------------------------------------------------------------------|----------------------------------------------------------------|
| `ESTIMATE_MAESTRO_STORE`       | `$XDG_DATA_HOME/estimate-maestro`, falling back to `~/.local/share/estimate-maestro` | Path to the store directory.                                   |
| `ESTIMATE_MAESTRO_DAY_START`   | `09:00`                                                                              | Start of the working day (ISO 8601 time).                      |
| `ESTIMATE_MAESTRO_DAY_END`     | `17:00`                                                                              | End of the working day (ISO 8601 time).                        |
| `ESTIMATE_MAESTRO_LUNCH_START` | `12:00`                                                                              | Start of the daily lunch break, excluded from working seconds. |
| `ESTIMATE_MAESTRO_LUNCH_END`   | `13:00`                                                                              | End of the daily lunch break.                                  |

The working-hours model has no other levers: the day boundaries and the lunch break are the whole of it. Anything more
would be collecting configuration for its own sake.

## The command-line tool

`estimate-maestro-cli` covers the everyday actions that do not need a conversation: `clock-in`, `clock-out`, `current`,
`record-absence`, `effort-table`, and `summary`.

Actions that only make sense as part of an estimating conversation — starting an effort, revising an estimate, recording
the final plan, harvesting commits — are MCP tools only, not CLI commands, on purpose: they are meant to happen inside a
session that shows comparable prior efforts, not as a bare command typed without that context.

### Exit codes

| Code | Meaning                                                                                                                                                  |
|------|----------------------------------------------------------------------------------------------------------------------------------------------------------|
| `0`  | Success.                                                                                                                                                 |
| `1`  | An error occurred.                                                                                                                                       |
| `3`  | `clock-out` only: nothing was clocked in. Expected, not a failure — a script wiring `clock-out` into an automatic hook should treat `3` the same as `0`. |

## Installation

Register the MCP server:

```sh
claude mcp add --scope user maestro-estimate -- uv --directory ~/mcp/estimate-maestro run estimate-maestro
```

The registered name inverts the directory name on purpose. On disk the server sits among other MCP servers, where
`estimate` is the half that distinguishes it and the half that sorts usefully; registered with an agent, `maestro` is
the more interesting half, because there the provenance is what matters — it marks the server as one of mine rather
than something installed from elsewhere.

Symlink the two skills into your personal skills directory:

```sh
ln -s ~/mcp/estimate-maestro/skills/recording-work-time ~/.claude/skills/recording-work-time
ln -s ~/mcp/estimate-maestro/skills/estimating-work ~/.claude/skills/estimating-work
```

Make the store a git repository. Its files are plain text and append-only so that it can be committed and roam between
machines, and it is the only surviving copy of what it records: a number lost or wrong in there cannot be reconstructed
from anywhere else. Keep it **private** — it holds project names, branch names and how long things took, none of which
belong in a public repo.

```sh
store="${XDG_DATA_HOME:-$HOME/.local/share}/estimate-maestro"
mkdir -p "$store"
git -C "$store" init
```

The default store location follows the XDG Base Directory Specification and needs no configuration. Set
`ESTIMATE_MAESTRO_STORE` only if you want the store somewhere else — for instance alongside your other personal
repositories, so it is easier to remember to commit and push. It must be visible to both the server and your shell, so
put it wherever they both read (typically your shell profile):

```sh
export ESTIMATE_MAESTRO_STORE=~/somewhere/else
```

Wire the two hook scripts into `~/.claude/settings.json`: `hooks/session-start.sh` as a `SessionStart` hook (reports
whether a timer is already running) and `hooks/session-end.sh` as a `SessionEnd` hook (closes a forgotten timer at the
configured end of the day):

```json
{
    "hooks": {
        "SessionStart": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "~/mcp/estimate-maestro/hooks/session-start.sh"
                    }
                ]
            }
        ],
        "SessionEnd": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "~/mcp/estimate-maestro/hooks/session-end.sh"
                    }
                ]
            }
        ]
    }
}
```

Merge that into the existing `hooks` block in `~/.claude/settings.json` rather than overwriting it, if one is already
there.

## Development

```sh
uv sync --locked
uv run ruff format --check
uv run ruff check
uv run pyright
uv run pytest src/ -v
```
