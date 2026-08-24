import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from estimate_maestro.models import Vcs

RECORD_SEPARATOR = "\x1e"
FIELD_SEPARATOR = "\x1f"


@dataclass(frozen=True)
class RepositoryReference:
    vcs: Vcs
    repository: str
    reference: str


@dataclass(frozen=True)
class CommitRecord:
    identifier: str
    subject: str
    authored_at: datetime
    files_changed: int
    insertions: int
    deletions: int


def _git(path: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments], cwd=path, check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError:
        return None
    return completed.stdout


def detect_repository(path: Path) -> RepositoryReference | None:
    path = Path(path).expanduser()
    if not path.is_dir():
        return None
    toplevel = _git(path, "rev-parse", "--show-toplevel")
    if toplevel is None:
        return None
    reference = _git(path, "rev-parse", "--abbrev-ref", "HEAD") or ""
    return RepositoryReference(
        vcs=Vcs.GIT, repository=Path(toplevel.strip()).name, reference=reference.strip()
    )


def _parse_numstat(lines: list[str]) -> tuple[int, int, int]:
    files_changed = insertions = deletions = 0
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        files_changed += 1
        insertions += int(parts[0]) if parts[0].isdigit() else 0
        deletions += int(parts[1]) if parts[1].isdigit() else 0
    return files_changed, insertions, deletions


def commits_between(path: Path, since: datetime, until: datetime) -> list[CommitRecord]:
    output = _git(
        Path(path).expanduser(),
        "log",
        f"--since={since.isoformat()}",
        f"--until={until.isoformat()}",
        "--reverse",
        "--numstat",
        f"--pretty=format:{RECORD_SEPARATOR}%H{FIELD_SEPARATOR}%s{FIELD_SEPARATOR}%aI",
    )
    if not output:
        return []
    harvested: list[CommitRecord] = []
    for block in output.split(RECORD_SEPARATOR):
        if not block.strip():
            continue
        lines = block.strip("\n").split("\n")
        identifier, subject, authored = lines[0].split(FIELD_SEPARATOR)
        files_changed, insertions, deletions = _parse_numstat(lines[1:])
        harvested.append(
            CommitRecord(
                identifier=identifier,
                subject=subject,
                authored_at=datetime.fromisoformat(authored),
                files_changed=files_changed,
                insertions=insertions,
                deletions=deletions,
            )
        )
    return harvested
