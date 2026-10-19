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

- **Fewer configuration levers.** The day boundaries and the lunch break are meant to be the whole of the working-hours
  model; anything more is collecting configuration for its own sake. That retires `ESTIMATE_MAESTRO_WORKDAYS` and
  `ESTIMATE_MAESTRO_OFF_HOURS_SESSION_CAP_MINUTES` with the change above, and turns
  `ESTIMATE_MAESTRO_DERIVE_LEAD_IN_MINUTES` and `ESTIMATE_MAESTRO_DERIVE_SESSION_GAP_MINUTES` into constants — and with
  them the start-up refusal when one exceeds the other. The editorial pass also left `ESTIMATE_MAESTRO_MINIMUM_EFFORTS`
  out of the documented configuration without saying so; whether it goes too is unsettled.

- **The default store is named `estimate-maestro-data`**, not `estimate-maestro`:
  `$XDG_DATA_HOME/estimate-maestro-data`, falling back to `~/.local/share/estimate-maestro-data`. The reasoning comes
  from the game library in `notes-jubilant-guacamole`, whose data repository is `Odalrick/game-library-data` on GitHub —
  though its local default is still plain `game-library`. The reasoning itself is not yet written down here.

  An existing store at the old default needs moving by hand; nothing migrates it.

## Open design questions

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
