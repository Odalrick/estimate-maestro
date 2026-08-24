import fcntl
import json
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

ESTIMATES_LOG = "estimates.jsonl"
SLICES_LOG = "slices.jsonl"
INTERVALS_LOG = "intervals.jsonl"
COMMITS_LOG = "commits.jsonl"
ABSENCES_LOG = "absences.jsonl"
META_FILE = "effort.json"
EFFORTS_DIRECTORY = "efforts"
SNAPSHOTS_DIRECTORY = "snapshots"


def _encode(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"cannot serialise {type(value).__name__}")


class Store:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser()

    def initialise(self) -> None:
        (self.root / EFFORTS_DIRECTORY).mkdir(parents=True, exist_ok=True)

    def effort_directory(self, effort: str) -> Path:
        return self.root / EFFORTS_DIRECTORY / effort

    def create_effort(self, effort: str, meta: dict[str, Any]) -> None:
        directory = self.effort_directory(effort)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / SNAPSHOTS_DIRECTORY).mkdir()
        self.write_meta(effort, meta)

    def write_meta(self, effort: str, meta: dict[str, Any]) -> None:
        path = self.effort_directory(effort) / META_FILE
        path.write_text(json.dumps(meta, indent=2, default=_encode) + "\n", encoding="utf-8")

    def read_meta(self, effort: str) -> dict[str, Any]:
        return json.loads((self.effort_directory(effort) / META_FILE).read_text(encoding="utf-8"))

    def _append_line(self, path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, default=_encode) + "\n"
        with path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.write(line)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read_lines(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def append(self, effort: str, log_name: str, record: dict[str, Any]) -> None:
        self._append_line(self.effort_directory(effort) / log_name, record)

    def read(self, effort: str, log_name: str) -> list[dict[str, Any]]:
        return self._read_lines(self.effort_directory(effort) / log_name)

    def append_absence(self, record: dict[str, Any]) -> None:
        self._append_line(self.root / ABSENCES_LOG, record)

    def read_absences(self) -> list[dict[str, Any]]:
        return self._read_lines(self.root / ABSENCES_LOG)

    def snapshot(self, effort: str, source: Path, label: str) -> str:
        source = Path(source).expanduser()
        stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
        name = f"{label}-{stamp}{source.suffix or '.md'}"
        destination = self.effort_directory(effort) / SNAPSHOTS_DIRECTORY / name
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        return name

    def list_efforts(self) -> list[str]:
        directory = self.root / EFFORTS_DIRECTORY
        if not directory.exists():
            return []
        return sorted(child.name for child in directory.iterdir() if child.is_dir())
