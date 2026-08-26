# Backlog

Wishlist and open questions. Not prioritised, not committed-to.

## Open design questions

- **Who commits the store, and when?** Undecided. The store is a git repository
  and the whole reason its files are append-only JSONL rather than SQLite is
  that it is "git-backed and roams between machines" — but nothing in the code
  commits it, and nothing prompts you to. Committing is currently manual and
  unprompted. The definition of done tests that the store *survives* a push and
  a pull; it never tested that the commits get made.

  Three candidates, to be settled by using the thing:

  - **Manual, but prompted.** The `SessionEnd` hook reports uncommitted store
    changes the way it reports a clamped clock-out, and commits nothing itself.
    Keeps control; costs a nudge that is easy to learn to ignore.
  - **Automatic on write.** Every recording operation commits, one commit per
    event. Nothing to forget, and git history becomes a second audit trail of
    the append-only log. Makes every `clock_in` a git write, and pushing still
    has to happen somehow.
  - **Automatic at session end.** The hook commits whatever changed, one commit
    per session. Coarse history, nothing to remember, and it matches the "a
    normal day is assumed, only deviations are recorded" posture the time model
    already takes.

  Pushing is a separate question from committing, and can stay manual under any
  of the three.

## Known gaps

- `annotate_interval` accepts an interval identifier that does not exist,
  recording an annotation nothing will ever read. Same shape as the
  `repair_interval` refusal, which was fixed; this one was scoped out.
- `repair_interval` accepts inverted bounds (`stop` before `start`) and records
  a clamped zero. A check covering only the both-bounds-given call would leave
  the commoner one-bound repair unvalidated while appearing to validate, so the
  gap was left visible rather than half-closed. The real fix recombines the
  proposed bound with the stored one before comparing.
- `Store.update_meta` and `Store.read_meta` raise a bare `FileNotFoundError` for
  an effort that does not exist. They cannot create anything, so there is no
  data hazard — it is only an unhelpful error.
- The MCP server reports an empty string as its version in the initialize
  handshake.
