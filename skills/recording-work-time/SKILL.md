---
name: recording-work-time
description: Use when work starts or stops on a tracked effort - starting an effort, clocking in and out, recording a slice insertion, closing a slice against its pull request, or running the final plan pass at a retrospective. Mechanical; carries no estimation reasoning.
---

# Recording work time

Strict and mechanical. Do these things at these moments. No judgement calls,
no interpretation, no estimation reasoning — this skill exists so that
referencing it does not pull estimation ideas into a working session.

## Starting an effort

`start_effort(title, kind, plan_path, summary_text, optimistic, likely,
pessimistic, rationale, work_slices)` creates the effort and takes the plan's
slice titles up front, as `work_slices`, a list of titles. This is not
incidental: the initial slice count is what makes later drift measurable.
Do not create the effort with an empty slice list and add slices afterwards
to get to the plan's real inventory — that throws away the baseline. Once the
effort is under way, `add_slice` is for slices that were not in that original
list — scope growth, not initial setup.

## When to clock in

- Starting work on a slice: `clock_in(effort, work_slice)`.
- Starting effort-level work with no slice — a design conversation, a
  retrospective: `clock_in(effort)`.
- A meeting that is part of the work: `clock_in(effort, kind="meeting",
  internal=<people we pay for, including the user>, external=<people we do not>)`.

`clock_in` refuses when an interval is already open. That refusal is correct;
clock out first rather than working around it.

`clock_in` also refuses when `work_slice` is given but is not a live slice on
that effort — closed, dropped, or simply mistyped — raising `UnknownSlice`. A
stale slice identifier is a plausible mistake mid-effort; treat the refusal as
a prompt to check the identifier, not as something to route around.

## When to clock out

- Finishing for the session, or switching slices: `clock_out()`.
- Forgot, and remembered later: `clock_out(at="<ISO 8601>")`.

A timer left running is closed by the `SessionEnd` hook, clamped to the
configured quit time. That is a normal outcome, not a failure — the model
assumes a normal day and only deviations need recording. The hook drives the
`estimate-maestro-cli` clock-out command, whose exit code tells the calling
script what happened: `0` means it clocked out successfully, `1` means a real
error, and `3` means nothing was clocked in — expected and frequent, not a
failure. Anyone wiring the hook should treat `3` the same as `0`, not as an
error to surface.

## When to record a deviation

- Time genuinely not worked — vacation, an appointment, an unrelated meeting,
  or anything else that does not fit those: `record_absence(start, stop,
  kind)`, where `kind` is one of `vacation`, `appointment`,
  `unrelated_meeting`, or `other`. Retroactive is expected and fine.
- An interval whose bounds were simply wrong: `repair_interval(effort,
  interval, start, stop)`.

Absence and repair are different: an absence says nobody was working anywhere
between those times; a repair says one specific interval was recorded wrongly.

## When to record scope movement

- A slice appears that was not in the plan: `add_slice(effort, title)`, then
  ask the user for a revised estimate and call `record_revision`. A slice
  inserted mid-flight is the cheapest moment to make drift visible.
- A slice turns out to be unnecessary: `drop_slice(effort, work_slice, reason)`.
- A slice's pull request merges: `close_slice(effort, work_slice, pull_request)`,
  then `record_landed_commit` with the squash commit on the default branch.
- History was rewritten by a rebase, amend, or fixup: `remap_commits(effort,
  old, new, reason)`.

## At the retrospective

`record_final_plan(effort, plan_path, summary_text, optimistic, likely,
pessimistic, rationale)`, then `finish_effort(effort)`.

**Never show the user a wall-time total during any of the above.** The
recording tools do not return one. Do not compute one yourself, and do not call
a calibration tool in a session where an estimate is being made.
