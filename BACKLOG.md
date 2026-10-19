# Backlog

Wishlist and open questions. Not prioritised, not committed-to.

## Pending changes

Decided, not yet built. The README describes the code as it is; these describe where it is going.

- **Every calendar day carries the same working hours.** Drop the concept of a non-working day, and with it the
  off-hours cap: a forgotten timer closes at the next end of the working day, whenever it started. A session started at
  22:00 on a Saturday and never ended is considered ended at 17:00 on the Sunday; one left running from 17:01 on a
  Friday closes at 17:00 on the Saturday. Today they close at 02:00 on the Sunday and 21:01 on the Friday, by the
  four-hour cap.

  The reasoning, from the README draft that first described it: an unreasonable time to record and unlikely to be
  accurate, but the simplicity makes the effects predictable, it bounds the damage at roughly a day, and the expectation
  is that the tooling remembers the clock-out — more reasonable times can be reconstructed from commit logs after the
  fact. Nothing recorded why the cap was four hours in the first place.

  It reaches further than clamping: `working_seconds_between` also skips non-working days, so commits made at a weekend
  would start counting as derived working time.

- **Revisit and prune the configuration.** Ten environment variables is setting-poison: entirely too many levers to
  tweak, each one a way for two machines to disagree about the same record.

  - `ESTIMATE_MAESTRO_STORE` stays, and is the only environment variable: it is the one setting that has to be known
    before the store can be found.
  - Whatever survives the prune moves into the store as a plain config file — JSON, JSONC or TOML, not yet chosen — so
    it is versioned with the data it shapes and roams with it.
  - Every other setting is either nuked or turned into a constant. `ESTIMATE_MAESTRO_DAY_START` looks useless: it only
    decides whether a forgotten timer started inside the working day (`clock.py:39`), and bounds working seconds on the
    commit-derived path nothing reaches. The lunch settings, likewise, only affect that unreachable path. The simpler
    time model above retires `ESTIMATE_MAESTRO_WORKDAYS` and `ESTIMATE_MAESTRO_OFF_HOURS_SESSION_CAP_MINUTES`; the two
    derive settings were already meant to become constants, taking the start-up refusal when one exceeds the other with
    them; and whether `ESTIMATE_MAESTRO_MINIMUM_EFFORTS` survives is unsettled.

  "Days" as the unit of time (below) may change which settings make sense at all, so settle that first.

- **The default store is named `estimate-maestro-data`**, not `estimate-maestro`:
  `$XDG_DATA_HOME/estimate-maestro-data`, falling back to `~/.local/share/estimate-maestro-data`. The store is a git
  repository in its own right, and it should not compete with the code repository for the same name: wherever the two
  meet — a GitHub account, a list of remotes, a backup — `estimate-maestro` is already the code. The game library's data
  repository follows the same reasoning (`Odalrick/game-library-data`).

  An existing store at the old default needs moving by hand; nothing migrates it.

- **Fix commit harvesting.** The intent was always a manual step that _backfills_ working time from commits, for work
  that was never clocked. The pieces exist but nothing reaches them:

  - `calibration.py` rebuilds sessions from harvested commits on every read (`_intervals_for`, via
    `timesheet.derive_intervals`), but only for a slice that has never been clocked in.
  - The only harvest the recording skill describes is of a clocked window — `current()`, `clock_out()`, then
    `harvest_commits` from the clock-in moment — so its commits always belong to a clocked slice, and the derivation
    skips them.
  - A single clock-in switches derivation off for the whole slice, so a day that was forgotten within a slice that was
    clocked on other days contributes nothing, even when its commits were harvested.
  - `remap_commits` records an event that nothing reads.

  Still to settle: backfilling the time no clocked interval covers, rather than switching per slice; whether backfilled
  intervals are recorded as events, with their provenance, or computed on every read as now; and the step in the
  recording skill that invokes it. The README says nothing about derived time until this exists.

## Open design questions

- **What gets stored, and when?** Review the event vocabulary down to what the five things need. The guess is that this
  suffices:

  - **start slice** and **still working on slice** — possibly one event;
  - **pause slice** and **end slice** — possibly one event;
  - the initial and follow-up estimates, with their details.

  Anything else is backfilled, with those same events — a backfilled start is a start, carrying its provenance, not a
  different kind of record. That makes commit backfill (above) and closing a forgotten timer (below) writers of the
  ordinary events rather than read-time special cases.

  For comparison, today's store keeps five logs per effort and a shared absence log: estimates (`initial`, `revision`,
  `final`), slices (`added`, `closed`, `dropped`, `renamed`), intervals (`clock_in`, `clock_out`, `annotate`, `repair`,
  with provenance `manual`, `clamped`, `derived_from_commits` or `repaired`), commits (`harvested`, `landed`, `remap`),
  and absences.

- **Time kept in days, not hours.** A "day" here is not a calendar day but an aggregate: an idea of a working day
  combined with a calendar day. Roughly, time logged on a slice within one calendar day, divided by six hours, capped at
  one. Parallel work is allowed, so one calendar day can add up to more than one day across slices — but never more than
  one for a single slice. The concept needs designing properly before anything is built on it.

  It reaches most of the rest: the working-hours model, the clamping of a forgotten timer, the lunch break, the pending
  simpler time model, and which settings survive the prune may all fall away or change shape once time is counted this
  way.

  The working name is **workdayish**. The "-ish" says plainly that it is an approximation rather than a measurement, and
  it cannot be mistaken for "working day" or "calendar day", which already mean specific things here. Still open: the
  plural ("3.5 workdayish" reads oddly) — perhaps the concept keeps the name while fields and output use a plainer
  count.

  Whatever the unit is called, its name joins the taint guard's `FORBIDDEN_NAME_PARTS` (`responses.py`) in the same
  change that introduces it, with a test that a response field carrying it is refused. The list has `"days"` but not
  `"day"`, so a `workdayish` field would pass the guard today.

- **What closes a forgotten timer?** Nothing, today. There were two Claude Code hooks — `SessionStart` reporting a
  running timer, `SessionEnd` clocking out — deleted on 2026-10-19 because they measured the wrong thing. They assumed
  one Claude Code session spans one working session, and it does not:

  - A session left open overnight fires nothing, so the timer ran until some session ended, possibly days later.
  - `SessionEnd` fires on `/clear` and on switching sessions with `/resume`, so it clocked out mid-work; before 17:00
    the clamp did not bound it.
  - `clock-out` closes whatever timer is running, so ending a session in any project, or in a terminal reused for
    something else, clocked out the effort.
  - The hook passed the moment the session ended as the last activity, so the recorded stop was never when work actually
    stopped.

  `SessionStart` was harmless, but fired again after every `/clear` and compaction. Whether `SessionEnd` fires at all
  when a terminal is closed or the process is killed is undocumented.

  Better signals exist: `UserPromptSubmit` and `Stop` fire on real activity, and inside the project. A hook could record
  the latest activity per working tree, and a clock-out could close at the last activity belonging to the effort — the
  CLI's `--at-last-activity` already takes that moment. Commit backfill (above) is the other half of the same problem.

- **Who commits the store, and when?** Undecided. The store is a git repository and the whole reason its files are
  append-only JSONL rather than SQLite is that it is "git-backed and roams between machines" — but nothing in the code
  commits it, and nothing prompts you to. Committing is currently manual and unprompted. The definition of done tests
  that the store _survives_ a push and a pull; it never tested that the commits get made.

  Three candidates, to be settled by using the thing:

  - **Manual, but prompted.** The `SessionEnd` hook reports uncommitted store changes the way it reports a clamped
    clock-out, and commits nothing itself. Keeps control; costs a nudge that is easy to learn to ignore.
  - **Automatic on write.** Every recording operation commits, one commit per event. Nothing to forget, and git history
    becomes a second audit trail of the append-only log. Makes every `clock_in` a git write, and pushing still has to
    happen somehow.
  - **Automatic at session end.** The hook commits whatever changed, one commit per session. Coarse history, nothing to
    remember, and it matches the "a normal day is assumed, only deviations are recorded" posture the time model already
    takes.

  Pushing is a separate question from committing, and can stay manual under any of the three.

  The first and third candidates were written against the `SessionEnd` hook, which is gone — see the forgotten-timer
  question above. A Claude Code session is no better a boundary for committing than for clocking out.

## Known gaps

- `annotate_interval` accepts an interval identifier that does not exist, recording an annotation nothing will ever
  read. Same shape as the `repair_interval` refusal, which was fixed; this one was scoped out.
- `repair_interval` accepts inverted bounds (`stop` before `start`) and records a clamped zero. A check covering only
  the both-bounds-given call would leave the commoner one-bound repair unvalidated while appearing to validate, so the
  gap was left visible rather than half-closed. The real fix recombines the proposed bound with the stored one before
  comparing.
- `Store.update_meta` and `Store.read_meta` raise a bare `FileNotFoundError` for an effort that does not exist. They
  cannot create anything, so there is no data hazard — it is only an unhelpful error.
- The MCP server reports an empty string as its version in the initialize handshake.
