---
name: estimating-work
description: Use when an estimate is needed for a piece of work about to start, or when re-estimating against a final plan at a retrospective. Shows comparable prior efforts; the user makes the estimate.
---

# Estimating work

**You do not make the estimate. The user does.** This skill's job is to put the
right comparisons in front of them.

## The method

Estimates are in story points, given as a three-point PERT triple: optimistic,
likely, and pessimistic. Points are anchored by comparison to prior efforts,
never by converting to hours in your head — the point of an abstract scale is
to compare apples to apples.

1. Call `reference_efforts()`.
2. Show the user the prior efforts whose summaries most resemble the work at
   hand, with their titles, summaries, and point triples. Where a prior
   effort also has a final-pass triple, show that alongside its initial one —
   but present it as what it is: a re-estimate made in hindsight about scope,
   not a report of how long the work took. It can be the closer comparison
   precisely because it reflects the plan as it actually turned out, not
   because it is a record of actual time spent.
3. Ask which ones it resembles and whether this is bigger or smaller.
4. Ask for the three numbers, and for a one-line rationale.
5. Ask for a one-or-two-paragraph summary of what this work is. It is the
   retrieval vector that makes the next estimate possible.

## What never enters this conversation

Wall time. Hours. Any actual. `reference_efforts` returns none, and no
calibration tool may be called in a session where an estimate is being made.
An estimate produced after seeing the total is an anchored echo of the actual,
not a calibration signal.

This matters most at the retrospective, where the final estimate is a
**counterfactual**: "given the plan as it actually turned out, what would you
have estimated?" — never "how long did it take?", and never a measurement of
any kind.

## Prior efforts, in full

`reference_efforts` returns summaries. The full archived plan artefacts live in
the store under each effort's `snapshots/` directory. Read the files inside
`snapshots/` when a summary is not enough to judge resemblance — and **read
nothing else in the store**. `intervals.jsonl` sits in the directory above,
holding every clock-in and clock-out, so an actual is one subtraction away from
anyone who opens it, and this is the one session in which that number must not
be seen.
