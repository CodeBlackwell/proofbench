"""The invariants that are the product: fail loud, never average around bad data."""
import subprocess

import pytest

from proofbench import util
from proofbench.engine import aggregate
from proofbench.judge import numeric_fields
from proofbench.util import HarnessError, extract_json


def test_extract_json_tolerates_prose_preamble():
    envelope = '{"result": "Here is the grade:\\n{\\"recall\\": 0.5}"}'
    assert extract_json(envelope) == {"recall": 0.5}


def test_extract_json_tolerates_markdown_fences():
    envelope = '{"result": "```json\\n{\\"recall\\": 1}\\n```"}'
    assert extract_json(envelope) == {"recall": 1}


def test_empty_envelope_is_fatal():
    with pytest.raises(HarnessError):
        extract_json("")


def test_no_json_object_is_fatal():
    # The ARG_MAX class of failure: the call aborted, result has no JSON. Must crash.
    with pytest.raises(HarnessError):
        extract_json('{"result": "the model only narrated, no object"}')


def test_numeric_fields_ignores_bools_and_strings():
    grade = {"recall": 0.5, "precision": 1, "ok": True, "task": "x"}
    assert numeric_fields(grade) == {"recall": 0.5, "precision": 1}


def test_aggregate_macro_averages_shared_numeric_fields():
    grades = [{"task": "a", "recall": 1.0, "precision": 1.0},
              {"task": "b", "recall": 0.0, "precision": 1.0}]
    board = aggregate(grades)
    assert board["macro_recall"] == 0.5
    assert board["macro_precision"] == 1.0


def _claude_prints(monkeypatch, returncode, stdout, stderr=""):
    """Stand in for the `claude` process, and report how it was started."""
    seen = {}

    def fake_run(argv, **kwargs):
        seen.update(argv=argv, **kwargs)
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)
    monkeypatch.setattr(util.subprocess, "run", fake_run)
    return seen


def test_the_judge_is_started_with_no_tools_and_no_ambient_config(monkeypatch):
    """The judge reads a diff an agent wrote. It grades text, so it gets nothing to act with,
    and nothing from the directory or the user it happens to be launched under."""
    seen = _claude_prints(monkeypatch, 0, '{"result": "{\\"recall\\": 1}"}')
    assert util.claude_json("grade this diff", "opus") == ({"recall": 1}, None)
    argv = seen["argv"]
    assert argv[argv.index("--tools") + 1] == ""
    assert "--safe-mode" in argv
    assert "--dangerously-skip-permissions" not in argv
    assert seen["input"] == "grade this diff" and "grade this diff" not in argv


def test_a_judge_process_that_fails_says_why(monkeypatch):
    _claude_prints(monkeypatch, 1, "", "error: unknown option '--safe-mode'")
    with pytest.raises(HarnessError, match="unknown option"):
        util.claude_json("grade this diff", "opus")
