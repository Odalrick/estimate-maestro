from datetime import datetime

from pydantic import ValidationError

from estimate_maestro.models import Estimate, EstimatePass
from estimate_maestro.responses import ReferenceEffort
from estimate_maestro.store import ESTIMATES_LOG, Store


def reference_efforts(
    store: Store, limit: int = 10, kind: str | None = None
) -> list[ReferenceEffort]:
    all_efforts = []
    for effort in store.list_efforts():
        meta = store.read_meta(effort)
        created_at = datetime.fromisoformat(meta["created_at"])
        all_efforts.append((created_at, effort, meta))

    all_efforts.sort(reverse=True, key=lambda x: (x[0], x[1]))

    references: list[ReferenceEffort] = []
    for _created_at, effort, meta in all_efforts:
        if kind is not None and meta.get("kind") != kind:
            continue
        initial = None
        final = None
        summary = ""
        try:
            for record in store.read(effort, ESTIMATES_LOG):
                if record["pass"] == EstimatePass.INITIAL:
                    initial = Estimate.model_validate(record["estimate"])
                    summary = record.get("summary", "")
                elif record["pass"] == EstimatePass.FINAL:
                    final = Estimate.model_validate(record["estimate"])
                    summary = record.get("summary") or summary
        except KeyError:
            continue
        except ValidationError:
            continue
        if initial is None:
            continue
        references.append(
            ReferenceEffort(
                effort=effort,
                title=meta["title"],
                kind=meta.get("kind", "other"),
                summary=summary,
                initial=initial,
                final=final,
            )
        )
        if len(references) >= limit:
            break
    return references
