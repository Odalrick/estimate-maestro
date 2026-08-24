from estimate_maestro.models import Estimate, EstimatePass
from estimate_maestro.responses import ReferenceEffort
from estimate_maestro.store import ESTIMATES_LOG, Store


def reference_efforts(
    store: Store, limit: int = 10, kind: str | None = None
) -> list[ReferenceEffort]:
    references: list[ReferenceEffort] = []
    for effort in reversed(store.list_efforts()):
        meta = store.read_meta(effort)
        if kind is not None and meta.get("kind") != kind:
            continue
        initial = None
        final = None
        summary = ""
        for record in store.read(effort, ESTIMATES_LOG):
            if record["pass"] == EstimatePass.INITIAL:
                initial = Estimate.model_validate(record["estimate"])
                summary = record.get("summary", "")
            elif record["pass"] == EstimatePass.FINAL:
                final = Estimate.model_validate(record["estimate"])
                summary = record.get("summary", summary)
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
        if len(references) == limit:
            break
    return references
