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
