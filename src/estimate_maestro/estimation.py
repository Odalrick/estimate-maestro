from datetime import datetime

from pydantic import ValidationError

from estimate_maestro.models import Estimate, EstimatePass
from estimate_maestro.responses import ReferenceEffort
from estimate_maestro.store import ESTIMATES_LOG, Store


def reference_efforts(
    store: Store, limit: int = 10, kind: str | None = None
) -> list[ReferenceEffort]:
    dated = []
    undated = []

    for effort in store.list_efforts():
        try:
            meta = store.read_meta(effort)
        except Exception:
            continue

        created_at = None
        try:
            created_at = datetime.fromisoformat(meta["created_at"])
        except KeyError:
            pass
        except ValueError:
            pass

        if created_at is not None:
            dated.append((created_at, effort, meta))
        else:
            undated.append((effort, meta))

    dated.sort(reverse=True, key=lambda x: (x[0], x[1]))
    undated.sort(key=lambda x: x[0])

    all_efforts = dated + [(None, e, m) for e, m in undated]

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
