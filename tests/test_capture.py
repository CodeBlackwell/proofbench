"""The repo task's git layer: what the agent is given, what it can reach, and what is graded.

Every test here failed against the layer that reset the corpus repo in place: a git failure
was read as an empty diff, the answer branch sat one `git checkout` away from the agent, and
a baseline named by branch moved when the agent committed on it."""
import subprocess

import pytest

from proofbench import capture
from proofbench.util import HarnessError

from .conftest import git


def test_a_branch_that_does_not_exist_is_a_hard_stop(repo):
    for default_branch, answer_branch in (("buggy", "fixxed"), ("bugy", "fixed")):
        with pytest.raises(HarnessError):
            capture.ground_truth(repo, default_branch, answer_branch)


def test_an_answer_that_changes_nothing_is_a_hard_stop(repo):
    with pytest.raises(HarnessError):
        capture.ground_truth(repo, "buggy", "buggy")


def test_a_path_inside_another_repo_is_refused_and_that_repo_is_left_alone(repo):
    inside = repo / "task"
    inside.mkdir()
    (repo / "a.py").write_text("uncommitted work\n")
    with pytest.raises(HarnessError):
        capture.ground_truth(inside, "buggy", "fixed")
    assert (repo / "a.py").read_text() == "uncommitted work\n"


def test_the_corpus_repo_is_never_modified(repo, tmp_path):
    (repo / "a.py").write_text("uncommitted work\n")
    (repo / ".env").write_text("SECRET=1\n")
    baseline, _ = capture.ground_truth(repo, "buggy", "fixed")
    work = capture.workspace(repo, "buggy", baseline, tmp_path / "work")
    (work / "a.py").write_text("x = 2\n")
    capture.capture(work, baseline)
    assert (repo / "a.py").read_text() == "uncommitted work\n"
    assert (repo / ".env").read_text() == "SECRET=1\n"
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "buggy"


def test_the_workspace_holds_the_baseline_and_no_way_to_the_answer(repo, tmp_path):
    baseline, _ = capture.ground_truth(repo, "buggy", "fixed")
    work = capture.workspace(repo, "buggy", baseline, tmp_path / "work")
    assert (work / "a.py").read_text() == "x = 1\n"
    assert "fixed" not in git(work, "branch", "-a")
    assert git(work, "remote") == ""
    assert git(repo, "rev-parse", "fixed") not in git(work, "cat-file", "--batch-all-objects",
                                                      "--batch-check")


def test_a_fix_committed_on_the_baseline_branch_is_still_captured(repo, tmp_path):
    baseline, _ = capture.ground_truth(repo, "buggy", "fixed")
    work = capture.workspace(repo, "buggy", baseline, tmp_path / "work")
    git(work, "checkout", "-q", "buggy")
    (work / "a.py").write_text("x = 2\n")
    git(work, "commit", "-qam", "agent fix")
    assert "+x = 2" in capture.capture(work, baseline)


def test_a_new_file_is_captured_and_a_dependency_tree_is_not(repo, tmp_path):
    baseline, _ = capture.ground_truth(repo, "buggy", "fixed")
    work = capture.workspace(repo, "buggy", baseline, tmp_path / "work")
    (work / "new.py").write_text("y = 3\n")
    (work / "node_modules").mkdir()
    (work / "node_modules" / "dep.js").write_text("z\n")
    diff = capture.capture(work, baseline)
    assert "+y = 3" in diff
    assert "dep.js" not in diff


def test_a_git_failure_while_capturing_is_a_hard_stop(tmp_path):
    with pytest.raises(HarnessError):
        capture.capture(tmp_path, "0" * 40)
    assert subprocess.run(["git", "-C", str(tmp_path), "status"], capture_output=True).returncode


@pytest.fixture
def noisy(repo):
    """The answer branch also carries a rebuilt bundle and a notes file: neither is the fix."""
    git(repo, "checkout", "-q", "fixed")
    (repo / "dist").mkdir()
    (repo / "dist" / "bundle.js").write_text("built\n")
    (repo / "notes.md").write_text("the answers\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "rebuild and notes")
    git(repo, "checkout", "-q", "buggy")
    return repo


def test_ignored_paths_are_left_out_of_the_answer(noisy):
    _, answer = capture.ground_truth(noisy, "buggy", "fixed", ["dist/**", "notes.md"])
    assert "+x = 2" in answer
    assert "bundle.js" not in answer and "notes.md" not in answer


def test_ignored_paths_are_left_out_of_what_the_agent_changed(noisy, tmp_path):
    baseline, _ = capture.ground_truth(noisy, "buggy", "fixed", ["dist/**"])
    work = capture.workspace(noisy, "buggy", baseline, tmp_path / "work")
    (work / "a.py").write_text("x = 2\n")
    (work / "dist").mkdir()
    (work / "dist" / "bundle.js").write_text("rebuilt by the agent\n")
    diff = capture.capture(work, baseline, ["dist/**"])
    assert "+x = 2" in diff and "bundle.js" not in diff


def test_ignoring_everything_the_answer_changes_is_a_hard_stop(noisy):
    with pytest.raises(HarnessError, match="no ground truth"):
        capture.ground_truth(noisy, "buggy", "fixed", ["**"])
