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
    # Two deliberate choices here, both load-bearing for the correctness of
    # every record this module writes.
    #
    # i18n.logOutputEncoding forces git to transcode message text to UTF-8 on
    # output. Git re-encodes to i18n.logOutputEncoding, which defaults to
    # i18n.commitEncoding rather than to UTF-8 — so a repository configured
    # with, say, ISO-8859-1 emits latin-1 bytes, and decoding those as UTF-8
    # would record a real commit under its real hash with a mangled subject.
    # Forcing the encoding makes git do the transcoding it already knows how
    # to do, and the decode below becomes lossless.
    #
    # Not text=True, because text mode applies universal-newline translation,
    # which rewrites a lone \r in git's output into a \n. Git stores and emits
    # a raw \r inside a commit subject unescaped, so under text mode a subject
    # arrives carrying a line break it does not actually contain, and every
    # line-positional parse below silently shifts. Decoding the raw bytes
    # ourselves keeps a \r a \r, where it can never manufacture a line
    # boundary.
    #
    # errors="replace" is the backstop underneath the forced encoding, and
    # should never fire once git is transcoding. If it somehow does, a
    # replacement character beats a UnicodeDecodeError escaping the three
    # exception types this function swallows and aborting a whole clock-out.
    # Correct first, survivable second.
    try:
        completed = subprocess.run(
            ["git", "-c", "i18n.logOutputEncoding=UTF-8", *arguments],
            cwd=path,
            check=True,
            capture_output=True,
        )
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
    # --no-show-signature because log.showSignature is an ordinary user
    # setting, and under it git prepends signature text to stdout ahead of
    # the --format output ("Good \"git\" signature for ..." on a verifiable
    # signature, "No signature" when verification cannot be performed).
    # That would land in lines[0] where the authored date belongs.
    output = _git(path, "show", "--no-show-signature", "--numstat", "--format=%aI%n%s", identifier)
    if output is None:
        return None
    # split("\n"), never splitlines(). splitlines() also breaks on \x0b, \x0c,
    # \x1c, \x1d, \x1e, \x85, \u2028 and \u2029, every one of which git passes
    # through a commit subject untouched. Swapping this for splitlines() would
    # read as a harmless modernisation and would silently reopen the entire
    # class of defect this parse exists to close: a subject able to forge a
    # line boundary, and with it a numstat row.
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
        "--no-show-signature",
        f"--since={since.isoformat()}",
        f"--until={until.isoformat()}",
        "--reverse",
        "--pretty=format:%H",
    )
    if not output:
        return []
    # A commit hash is 40 hex characters: it cannot contain a newline or
    # any other separator, so this list is unforgeable no matter what a
    # commit's subject contains. split("\n") rather than splitlines() for the
    # reason spelled out in _commit_detail.
    identifiers = [line for line in output.split("\n") if line.strip()]
    harvested: list[CommitRecord] = []
    for identifier in identifiers:
        detail = _commit_detail(path, identifier)
        if detail is not None:
            harvested.append(detail)
    return harvested
