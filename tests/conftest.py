"""A two branch repo built per test, so the repo task is tested without the demo corpus."""
import subprocess

import pytest

IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *IDENTITY, *args],
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """`buggy` holds x = 1 and is checked out; `fixed` holds x = 2."""
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-q", "-b", "buggy")
    (source / "README.md").write_text("Fix x.\n")
    (source / "a.py").write_text("x = 1\n")
    git(source, "add", ".")
    git(source, "commit", "-qm", "buggy")
    git(source, "checkout", "-qb", "fixed")
    (source / "a.py").write_text("x = 2\n")
    git(source, "commit", "-qam", "fixed")
    git(source, "checkout", "-q", "buggy")
    return source
