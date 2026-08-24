import re
import uuid
from collections.abc import Callable
from datetime import date

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    return _NON_ALPHANUMERIC.sub("-", text.lower()).strip("-")


def effort_identifier(created_on: date, title: str) -> str:
    return f"{created_on.isoformat()}-{slugify(title)}"


def _random_suffix() -> str:
    return uuid.uuid4().hex[:8]


def new_identifier(prefix: str, source: Callable[[], str] = _random_suffix) -> str:
    return f"{prefix}-{source()}"
