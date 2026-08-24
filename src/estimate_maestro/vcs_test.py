import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from estimate_maestro.models import Vcs
from estimate_maestro.vcs import commits_between, detect_repository

BASE = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)


def git(path: Path, *arguments: str, moment: datetime | None = None) -> None:
    environment = None
    if moment is not None:
        stamp = moment.isoformat()
        environment = {
            "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_DATE": stamp,
            "PATH": "/usr/bin:/bin",
            "HOME": str(path),
        }
    subprocess.run(["git", *arguments], cwd=path, check=True, capture_output=True, env=environment)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    for index in range(3):
        (path / f"file{index}.txt").write_text(f"line {index}\n")
        git(path, "add", ".")
        git(path, "commit", "-m", f"commit {index}", moment=BASE + timedelta(hours=index))
    return path


def test_a_git_checkout_is_detected_with_its_branch(repository: Path):
    detected = detect_repository(repository)

    assert detected is not None
    assert detected.vcs is Vcs.GIT
    assert detected.repository == "repo"
    assert detected.reference == "main"


def test_a_directory_that_is_not_a_repository_detects_as_none(tmp_path: Path):
    assert detect_repository(tmp_path / "nowhere") is None


def test_commits_in_the_window_are_returned_oldest_first(repository: Path):
    harvested = commits_between(
        repository, since=BASE - timedelta(minutes=1), until=BASE + timedelta(hours=5)
    )

    assert [record.subject for record in harvested] == ["commit 0", "commit 1", "commit 2"]
    assert harvested[0].authored_at == BASE


def test_commits_outside_the_window_are_excluded(repository: Path):
    harvested = commits_between(
        repository, since=BASE + timedelta(minutes=30), until=BASE + timedelta(hours=5)
    )

    assert [record.subject for record in harvested] == ["commit 1", "commit 2"]


def test_a_diffstat_is_captured(repository: Path):
    harvested = commits_between(
        repository, since=BASE - timedelta(minutes=1), until=BASE + timedelta(hours=5)
    )

    assert harvested[0].files_changed == 1
    assert harvested[0].insertions == 1
    assert harvested[0].deletions == 0


def test_a_subject_containing_the_field_separator_survives_intact(tmp_path: Path):
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    (path / "file.txt").write_text("line\n")
    git(path, "add", ".")
    git(path, "commit", "-m", "before\x1fafter", moment=BASE)

    harvested = commits_between(
        path, since=BASE - timedelta(minutes=1), until=BASE + timedelta(hours=1)
    )

    assert [record.subject for record in harvested] == ["before\x1fafter"]


def test_a_subject_containing_the_record_separator_survives_intact(tmp_path: Path):
    # Under the hash-list-then-per-commit-detail scheme, a record separator
    # in a subject no longer costs the commit anything: there is nothing
    # left in the parse for it to corrupt.
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    for index, subject in enumerate(["commit 0", "before\x1eafter", "commit 2"]):
        (path / f"file{index}.txt").write_text(f"line {index}\n")
        git(path, "add", ".")
        git(path, "commit", "-m", subject, moment=BASE + timedelta(hours=index))

    harvested = commits_between(
        path, since=BASE - timedelta(minutes=1), until=BASE + timedelta(hours=5)
    )

    subjects = [record.subject for record in harvested]
    assert subjects == ["commit 0", "before\x1eafter", "commit 2"]
    assert len(harvested) == 3


def test_a_subject_containing_both_separators_together_is_harvested_intact(tmp_path: Path):
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    for index, subject in enumerate(["commit 0", "before\x1f\x1eafter", "commit 2"]):
        (path / f"file{index}.txt").write_text(f"line {index}\n")
        git(path, "add", ".")
        git(path, "commit", "-m", subject, moment=BASE + timedelta(hours=index))

    harvested = commits_between(
        path, since=BASE - timedelta(minutes=1), until=BASE + timedelta(hours=5)
    )

    assert len(harvested) == 3
    assert [record.subject for record in harvested] == [
        "commit 0",
        "before\x1f\x1eafter",
        "commit 2",
    ]
    assert harvested[1].files_changed == 1
    assert harvested[1].insertions == 1
    assert harvested[1].deletions == 0


def test_a_subject_containing_a_carriage_return_survives_intact(tmp_path: Path):
    # Git emits a raw \r inside a subject unescaped. Decoding git's output
    # under universal-newline translation would turn it into a line break and
    # truncate the subject at it.
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    (path / "file.txt").write_text("line\n")
    git(path, "add", ".")
    git(path, "commit", "-m", "before\rafter", moment=BASE)

    harvested = commits_between(
        path, since=BASE - timedelta(minutes=1), until=BASE + timedelta(hours=1)
    )

    assert len(harvested) == 1
    assert [record.subject for record in harvested] == ["before\rafter"]
    assert harvested[0].files_changed == 1
    assert harvested[0].insertions == 1
    assert harvested[0].deletions == 0


def test_a_subject_cannot_forge_a_numstat_row_with_a_carriage_return(tmp_path: Path):
    # The forgery case: a \r followed by text shaped exactly like a numstat
    # row. If the \r ever became a line break, this line would be parsed as a
    # real diff row and fold attacker-chosen numbers into the true diffstat.
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    (path / "file.txt").write_text("line\n")
    git(path, "add", ".")
    git(path, "commit", "-m", "before\r5\t3\tfake.txt", moment=BASE)

    harvested = commits_between(
        path, since=BASE - timedelta(minutes=1), until=BASE + timedelta(hours=1)
    )

    assert len(harvested) == 1
    assert [record.subject for record in harvested] == ["before\r5\t3\tfake.txt"]
    assert harvested[0].files_changed == 1
    assert harvested[0].insertions == 1
    assert harvested[0].deletions == 0


def test_a_subject_stored_in_a_non_utf_8_encoding_round_trips_correctly(tmp_path: Path):
    # i18n.logOutputEncoding defaults to i18n.commitEncoding, not to UTF-8, so
    # without forcing it git emits latin-1 bytes here and the subject would be
    # recorded with replacement characters instead of the real ones.
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    git(path, "config", "i18n.commitEncoding", "ISO-8859-1")
    (path / "message.txt").write_bytes("kafé pausé\n".encode("iso-8859-1"))
    (path / "file.txt").write_text("line\n")
    git(path, "add", "file.txt")
    git(path, "commit", "-F", "message.txt", moment=BASE)

    harvested = commits_between(
        path, since=BASE - timedelta(minutes=1), until=BASE + timedelta(hours=1)
    )

    assert len(harvested) == 1
    assert [record.subject for record in harvested] == ["kafé pausé"]
    assert "�" not in harvested[0].subject
    assert harvested[0].files_changed == 1
    assert harvested[0].insertions == 1
    assert harvested[0].deletions == 0


def test_a_signed_commit_is_harvested_when_log_show_signature_is_set(tmp_path: Path):
    # log.showSignature makes git prepend signature text to stdout ahead of
    # the --format output, which would land where the authored date is read.
    if shutil.which("ssh-keygen") is None:
        pytest.skip("ssh-keygen is needed to create a signed commit")
    key = tmp_path / "signing-key"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key), "-C", "test"],
        check=True,
        capture_output=True,
    )
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    git(path, "config", "gpg.format", "ssh")
    git(path, "config", "user.signingkey", str(key.with_suffix(".pub")))
    git(path, "config", "commit.gpgsign", "true")
    git(path, "config", "log.showSignature", "true")
    (path / "file.txt").write_text("line\n")
    git(path, "add", ".")
    git(path, "commit", "-m", "signed subject", moment=BASE)

    harvested = commits_between(
        path, since=BASE - timedelta(minutes=1), until=BASE + timedelta(hours=1)
    )

    assert len(harvested) == 1
    assert [record.subject for record in harvested] == ["signed subject"]
    assert harvested[0].authored_at == BASE
    assert harvested[0].files_changed == 1
    assert harvested[0].insertions == 1
    assert harvested[0].deletions == 0
