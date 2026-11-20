"""A repo task may fix its own ground-truth items.

Left to itself the judge reads every distinct change in the answer as an item, so an answer
that also rewords docstrings scored an agent 1 of 7 for fixing one of the two things that were
broken. With `items`, the corpus author says what counts, the judge only rules on each one,
and the harness does the division: the denominator is no longer the judge's to choose."""
import pytest

from proofbench import judge
from proofbench.util import HarnessError

ITEMS = ["a notified waiter that is cancelled passes the wakeup on",
         "the wakeup is also passed on when the cancel lands while re-acquiring the lock"]


def verdicts(*fixed):
    return [{"id": f"i{number}", "fixed_by_agent": one} for number, one in enumerate(fixed, 1)]


def grade(monkeypatch, reply, items=ITEMS):
    """Grade with a stub judge. Returns the grade and the prompt the judge was sent."""
    seen = {}
    monkeypatch.setattr(judge, "claude_json", lambda prompt, model: seen.update(prompt=prompt) or reply)
    return judge.grade("grade it", "the readme", "the answer", "the agent diff", "opus", items), seen["prompt"]


def test_the_judge_is_shown_each_item_under_its_id(monkeypatch):
    _, prompt = grade(monkeypatch, {"items": verdicts(True, True), "precision": 1.0})
    assert f"i1: {ITEMS[0]}" in prompt and f"i2: {ITEMS[1]}" in prompt
    assert prompt.index("GROUND_TRUTH_ITEMS") < prompt.index("===== ANSWER_DIFF =====")


def test_recall_is_counted_by_the_harness_whatever_the_judge_claims(monkeypatch):
    graded, _ = grade(monkeypatch, {"items": verdicts(True, False), "recall": 1.0, "precision": 0.5})
    assert graded["recall"] == 0.5
    assert graded["precision"] == 0.5


@pytest.mark.parametrize("items", [
    verdicts(True),                                         # one verdict short
    verdicts(True, False, True),                            # an item the task never listed
    [{"id": "i1", "fixed_by_agent": True}] * 2,             # the same id twice
    [{"id": "i1", "fixed_by_agent": True}, {"id": "second", "fixed_by_agent": True}],
    [{"id": "i1", "fixed_by_agent": True}, {"id": "i2", "fixed_by_agent": "yes"}],
    "i1 and i2 are both fixed",
    None,
])
def test_a_reply_that_does_not_rule_on_exactly_the_listed_items_is_a_hard_stop(monkeypatch, items):
    with pytest.raises(HarnessError, match="items"):
        grade(monkeypatch, {"items": items, "recall": 1.0, "precision": 1.0})


def test_a_task_without_items_is_graded_as_before(monkeypatch):
    graded, prompt = grade(monkeypatch, {"recall": 0.14, "precision": 1.0}, items=[])
    assert graded == {"recall": 0.14, "precision": 1.0}
    assert "GROUND_TRUTH_ITEMS" not in prompt
