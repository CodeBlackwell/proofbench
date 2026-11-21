"""What a leg may call its own numbers.

The suite went green over a corpus that is unanswerable by construction: the study's eight
verified absences, every line of them `"answerable": false`. The leg printed `accuracy 1.0` and
`tokens_per_correct 205`, and the word abstention reached no part of the run path. The question set's own README says a
number off that file is an abstention rate and that reporting it as accuracy is a category
error, but the README is not what prints.

Offline, and no arm runs: every case here is built from graded records."""
import itertools
import unittest

from proofbench import engine, scoreboard
from proofbench.util import HarnessError

TOKENS_PER_QUESTION = 205          # 190 in, 15 out, the shape an arm reports
# Records sharing an id are trials of one question, so every record here takes its own.
SERIAL = itertools.count(1)


def record(correct, answerable=True, abstained=False):
    return {"id": f"UQ-{next(SERIAL):04d}", "correct": correct, "graded_by": "abstention",
            "abstained": abstained, "answerable": answerable,
            "tokens_in": 190, "tokens_out": 15,
            "question": {"type": "unanswerable"}}


def absences():
    """questions/lineage.jsonl in shape: eight unanswerables, every one correctly abstained
    on."""
    return [record(1, answerable=False, abstained=True) for _ in range(8)]


class AbstentionOnlyLeg(unittest.TestCase):
    """A corpus of verified absences measures one thing, and may name only that thing."""

    def setUp(self):
        self.leg = scoreboard.metrics(absences())

    def test_no_key_named_accuracy_exists_to_be_lifted(self):
        self.assertNotIn("accuracy", self.leg)
        self.assertNotIn("tokens_per_correct", self.leg)

    def test_what_it_measured_is_named_abstention(self):
        self.assertEqual(self.leg["measures"], "abstention only")
        self.assertEqual(self.leg["abstention_rate"], 1.0)
        self.assertEqual(self.leg["tokens_per_correct_abstention"], float(TOKENS_PER_QUESTION))

    def test_the_counts_that_decide_it_print_beside_it(self):
        self.assertEqual((self.leg["questions"], self.leg["answerable"],
                          self.leg["unanswerable"]), (8, 0, 8))

    def test_the_objective_a_config_asks_for_is_a_hard_stop_here(self):
        """The arm configs optimise tokens_per_correct. Against this corpus proofbench refuses
        rather than pricing correct answers nobody gave."""
        with self.assertRaises(HarnessError) as raised:
            engine.objective_of(self.leg, "tokens_per_correct")
        self.assertIn("not in scoreboard", str(raised.exception))

    def test_one_answerable_question_brings_the_accuracy_names_back(self):
        leg = scoreboard.metrics(absences() + [record(1)])
        self.assertEqual(leg["measures"], "accuracy and abstention")
        self.assertEqual(leg["accuracy"], 1.0)


class NotAbstainingIsNotBeingCorrect(unittest.TestCase):

    def test_an_arm_wrong_on_every_answerable_question_scores_one(self):
        """The rate counts the arms that answered, not the arms that were right, so the word
        correct had no business in its name: this leg scores 1.0 on it at accuracy 0.0."""
        leg = scoreboard.metrics([record(0), record(0)])
        self.assertEqual(leg["non_abstention_rate_answerable"], 1.0)
        self.assertEqual(leg["accuracy"], 0.0)
        self.assertNotIn("abstention_correct_answerable", leg)


if __name__ == "__main__":
    unittest.main()
