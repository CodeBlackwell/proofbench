"""The replay runner: a stored patch stands in for an agent, so a known diff can be graded."""
from pathlib import Path

from proofbench import capture, runner

REPLAY = Path(__file__).resolve().parent.parent / "corpora" / "replay.sh"


def _replay(repo, tmp_path, patch_text):
    baseline, answer = capture.ground_truth(repo, "buggy", "fixed")
    patch = tmp_path / "stored.patch"
    patch.write_text(patch_text if patch_text is not None else answer)
    work = capture.workspace(repo, "buggy", baseline, tmp_path / "work")
    runner.run(str(REPLAY), str(patch), "no-model", 1, work, tmp_path / "run.log")
    return answer, capture.capture(work, baseline)


def test_a_replayed_answer_is_captured_byte_for_byte(repo, tmp_path):
    answer, captured = _replay(repo, tmp_path, None)
    assert captured == answer


def test_a_patch_that_does_not_apply_leaves_an_empty_capture_and_says_why(repo, tmp_path):
    """The harness flags an empty capture, so a stored patch that has gone stale is seen."""
    stale = "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = 99\n+x = 2\n"
    _, captured = _replay(repo, tmp_path, stale)
    assert captured == ""
    assert "patch failed" in (tmp_path / "run.log").read_text()
