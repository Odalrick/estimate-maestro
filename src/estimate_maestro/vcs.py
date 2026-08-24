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
    # Deliberately not text=True. Text mode applies universal-newline
    # translation, which rewrites a lone \r in git's output into a \n. Git
    # stores and emits a raw \r inside a commit subject unescaped, so under
    # text mode a subject arrives carrying a line break it does not actually
    # contain, and every line-positional parse below silently shifts. Decoding
    # the raw bytes ourselves keeps a \r a \r, where it can never manufacture
    # a line boundary. errors="replace" because a decode failure here would
    # escape the three exception types this function swallows and abort a
    # whole clock-out; best effort matches the posture of the rest of the
    # function.
    try:
        completed = subprocess.run(["git", *arguments], cwd=path, check=True, capture_output=True)
    except subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError:
        return None
    return completed.stdout.decode("utf-8", errors="replace")


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
    # Positional, not separator-based: %aI and %s are each exactly one line
    # of git's output, so there is no data-derived byte for a malicious or
    # merely unlucky commit to forge a boundary with. A hash is passed in
    # from the unforgeable list below, never parsed out of message text.
    # This holds only because _git decodes raw bytes: a subject is the
    # message's first line in the git object, but it can still contain a
    # raw \r, which universal-newline translation would turn into a real
    # line break here and shift every line after it.
    output = _git(path, "show", "--numstat", "--format=%aI%n%s", identifier)
    if output is None:
        return None
    lines = output.split("\n")
    if len(lines) < 2:
        return None
    authored, subject = lines[0], lines[1]
    # A merge commit may or may not produce numstat rows here, depending on
    # the git version and the options in play: git 2.55's `git show` prints a
    # diffstat against the first parent, while other versions and option
    # combinations print none at all. The parser treats both the same, so an
    # all-zero diffstat on a merge is git's own semantics, not a parser bug.
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
