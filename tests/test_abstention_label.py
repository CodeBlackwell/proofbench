"""What a leg may call its own numbers, and what a grid may leave out of itself.

The suite went green over a corpus that is unanswerable by construction: the study's eight
verified absences, every line of them `"answerable": false`. The leg printed `accuracy 1.0` and
`tokens_per_correct 205`, the grid printed 1.0 in each of the two cells it drew out of fifteen,
and the word abstention reached no part of the run path. The question set's own README says a
number off that file is an abstention rate and that reporting it as accuracy is a category
error, but the README is not what prints.

Offline, and no arm runs: every case here is built from graded records."""
import unittest

from proofbench import engine, scoreboard
from proofbench.util import HarnessError

TOKENS_PER_QUESTION = 205          # 190 in, 15 out, the shape an arm reports


def record(correct, answerable=True, abstained=False, tier=1, hops=1):
    return {"id": f"UQ-{tier}{hops}", "correct": correct, "graded_by": "abstention",
            "abstained": abstained, "answerable": answerable,
            "tokens_in": 190, "tokens_out": 15,
            "question": {"tier": tier, "hops": hops, "type": "unanswerable"}}


def absences():
    """questions/lineage.jsonl in shape: eight unanswerables over two of the fifteen cells,
    five at tier 1 and three at tier 3, every one correctly abstained on."""
    return [record(1, answerable=False, abstained=True, tier=tier)
            for tier in (1, 1, 1, 1, 1, 3, 3, 3)]


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


class GridGaps(unittest.TestCase):
    """The axes are the stratification the PRD fixes, so the table cannot hide its own holes."""

    def printed(self, records, metric):
        return scoreboard.grid(records, "tier", "hops", metric).splitlines()

    def test_two_cells_of_fifteen_still_print_fifteen(self):
        lines = self.printed(absences(), "abstention_rate")
        self.assertEqual(lines[0], "abstention_rate by tier x hops")
        self.assertEqual(lines[3].split("|")[1].split(), ["1.0", ".", ".", ".", "."])
        self.assertEqual(lines[4].split("|")[1].split(), [".", ".", ".", ".", "."])
        self.assertEqual(lines[5].split("|")[1].split(), ["1.0", ".", ".", ".", "."])

    def test_a_cell_holding_questions_but_no_such_number_is_not_an_empty_cell(self):
        self.assertEqual(self.printed(absences(), "accuracy")[3].split("|")[1].split(),
                         ["-", ".", ".", ".", "."])

    def test_an_axis_the_stratification_does_not_fix_is_a_hard_stop(self):
        with self.assertRaises(HarnessError) as raised:
            scoreboard.grid(absences(), "tier", "type", "abstention_rate")
        self.assertIn("not a stratification axis", str(raised.exception))

    def test_a_question_off_the_axes_is_a_hard_stop(self):
        with self.assertRaises(HarnessError) as raised:
            scoreboard.grid([record(1, tier=4)], "tier", "hops", "accuracy")
        self.assertIn("outside the stratification", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
