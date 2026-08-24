import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from estimate_maestro.models import Vcs


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


def _commit_detail(path: Path, identifier: str) -> CommitRecord | None:
    # Positional, not separator-based: %aI and %s are each guaranteed to be
    # exactly one line (a subject is by definition a message's first line,
    # so it cannot itself contain a newline), so there is no data-derived
    # byte for a malicious or merely unlucky commit to forge a boundary
    # with. A hash is passed in from the unforgeable list below, never
    # parsed out of message text.
    output = _git(path, "show", "--numstat", "--format=%aI%n%s", identifier)
    if output is None:
        return None
    lines = output.split("\n")
    if len(lines) < 2:
        return None
    authored, subject = lines[0], lines[1]
    # A merge commit legitimately has no numstat rows under --numstat, so
    # files_changed == insertions == deletions == 0 for one is git's own
    # semantics, not a parser bug.
    files_changed, insertions, deletions = _parse_numstat(
        [line for line in lines[2:] if line.strip()]
    )
    return CommitRecord(
        identifier=identifier,
        subject=subject,
        authored_at=datetime.fromisoformat(authored),
        files_changed=files_changed,
        insertions=insertions,
        deletions=deletions,
    )


def commits_between(path: Path, since: datetime, until: datetime) -> list[CommitRecord]:
    path = Path(path).expanduser()
    output = _git(
        path,
        "log",
        f"--since={since.isoformat()}",
        f"--until={until.isoformat()}",
        "--reverse",
        "--pretty=format:%H",
    )
    if not output:
        return []
    # A commit hash is 40 hex characters: it cannot contain a newline or
    # any other separator, so this list is unforgeable no matter what a
    # commit's subject contains.
    identifiers = [line for line in output.split("\n") if line.strip()]
    harvested: list[CommitRecord] = []
    for identifier in identifiers:
        detail = _commit_detail(path, identifier)
        if detail is not None:
            harvested.append(detail)
    return harvested
