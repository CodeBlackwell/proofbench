"""The invariants that are the product: fail loud, never average around bad data."""
import pytest

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
