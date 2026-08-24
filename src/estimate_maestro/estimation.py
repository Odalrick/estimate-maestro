from datetime import datetime
from typing import Any

from estimate_maestro.models import Estimate, EstimatePass
from estimate_maestro.responses import ReferenceEffort
from estimate_maestro.store import ESTIMATES_LOG, Store


def _creation_moment(meta: dict[str, Any]) -> datetime | None:
    """The moment an effort was created, or None when the stored value is unusable.

    A usable creation timestamp is a timezone-aware datetime. A missing key, a
    non-string value, an unparseable string and a naive datetime are all equally
    unusable, and every one of them lands in the undated bucket that sorts last.

    Naive values are not coerced to a timezone: picking an offset for them would
    invent ordering data the record does not have, and a naive value mixed into
    the sort compares against an aware one by raising, taking the whole listing
    down. Treating naive as undated keeps every timestamp in the sort aware by
    construction, so the comparison cannot raise.
    """
    stored = meta.get("created_at")
    if not isinstance(stored, str):
        return None
    try:
        moment = datetime.fromisoformat(stored)
    except ValueError:
        return None
    if moment.utcoffset() is None:
        return None
    return moment


def _readable_meta(store: Store, effort: str) -> dict[str, Any] | None:
    """The effort's meta, or None when `effort.json` cannot be read as an object.

    A missing file, unreadable file or unparseable JSON leaves nothing to show,
    and so does a file holding something other than a JSON object: every read of
    `meta` below that point would raise on it.
    """
    try:
        meta = store.read_meta(effort)
    except OSError, ValueError:
        return None
    if not isinstance(meta, dict):
        return None
    return meta


def _reference_effort(store: Store, effort: str, meta: dict[str, Any]) -> ReferenceEffort | None:
    """One effort's reference view, or None when it carries no initial estimate.

    Raises whatever a malformed record raises — the caller turns that into the
    same skip, because the store's job is to protect the record and this view's
    job is to show what it can read.
    """
    initial = None
    final = None
    summary = ""
    for record in store.read(effort, ESTIMATES_LOG):
        if record["pass"] == EstimatePass.INITIAL:
            initial = Estimate.model_validate(record["estimate"])
            summary = record.get("summary", "")
        elif record["pass"] == EstimatePass.FINAL:
            final = Estimate.model_validate(record["estimate"])
            summary = record.get("summary") or summary
    if initial is None:
        return None
    return ReferenceEffort(
        effort=effort,
        title=meta["title"],
        kind=meta.get("kind", "other"),
        summary=summary,
        initial=initial,
        final=final,
    )


def reference_efforts(
    store: Store, limit: int = 10, kind: str | None = None
) -> list[ReferenceEffort]:
    dated: list[tuple[datetime, str, dict[str, Any]]] = []
    undated: list[tuple[str, dict[str, Any]]] = []

    for effort in store.list_efforts():
        meta = _readable_meta(store, effort)
        if meta is None:
            continue

        created_at = _creation_moment(meta)
        if created_at is None:
            undated.append((effort, meta))
        else:
            dated.append((created_at, effort, meta))

    dated.sort(reverse=True, key=lambda entry: (entry[0], entry[1]))
    # Undated efforts have no order of their own, so identifier order stands in — sorted
    # here rather than inherited from whatever order `list_efforts` happens to return.
    undated.sort(key=lambda entry: entry[0])

    ordered = [(effort, meta) for _created_at, effort, meta in dated] + undated

    references: list[ReferenceEffort] = []
    for effort, meta in ordered:
        if kind is not None and meta.get("kind") != kind:
            continue
        # Malformed data reaches here as a missing key, a value of the wrong type or a
        # failed validation (pydantic's ValidationError and the store's MalformedRecord
        # are both ValueError). One unreadable effort costs its own row, not the listing.
        try:
            reference = _reference_effort(store, effort, meta)
        except KeyError, TypeError, ValueError:
            continue
        if reference is None:
            continue
        references.append(reference)
        if len(references) >= limit:
            break
    return references
