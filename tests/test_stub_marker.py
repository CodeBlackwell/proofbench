"""The scoreboard a canned leg writes, which is the file the study's registry scans.

The suite went green over a canned run that read as a measured one. Every arm reports whether a
canned reply answered it, the grader dropped that field, and so scoreboard.json, the one artefact a
reader and a checker both open, could not carry it. Nothing here exercised a scoreboard written
from a stubbed leg, which is exactly why nothing caught it.

Offline, like the rest: the arm is a stub executable and the judge is never reached, because every
question grades on an exact id match."""
import json
import stat
import tempfile
import unittest
from pathlib import Path

from proofbench import config, question, scoreboard
from proofbench.util import HarnessError

QUESTIONS = [
    {"id": "LQ-0001", "text": "Who advised Carl Friedrich Gauss?", "answer": ["Q77361"],
     "answer_names": ["Johann Friedrich Pfaff"], "answerable": True, "tier": 1, "hops": 1,
     "type": "lookup"},
    {"id": "LQ-0002", "text": "Who advised Richard Feynman?", "answer": ["Q202631"],
     "answer_names": ["John Archibald Wheeler"], "answerable": True, "tier": 1, "hops": 1,
     "type": "lookup"},
]

ARM_BODY = """question = json.loads(sys.stdin.read())
print(json.dumps({"answer": ", ".join(question["answer_names"]),
                  "answer_ids": question["answer"], "abstained": False,
                  "tokens_in": 100, "tokens_out": 10, "seconds": 0.0,
                  **REPORT}))
"""

CONFIG = """runner: arm.py
models: [claude-sonnet-5]
judge_model: claude-opus-5
objective: tokens_per_correct
judge: judge.md

corpus:
  - kind: question
    file: questions.jsonl
"""


def record(stubbed=None, model=None, cost_usd=None):
    """One graded record in the shape _ask_and_grade now builds, for the leg level facts alone."""
    return {"id": "LQ-0001", "correct": 1, "graded_by": "exact", "abstained": False,
            "answerable": True, "tokens_in": 100, "tokens_out": 10, "cost_usd": cost_usd,
            "seconds": 0.0, "stubbed": stubbed, "model": model,
            "question": {"tier": 1, "hops": 1, "type": "lookup"}}


class LegProvenance(unittest.TestCase):
    """The facts that decide whether a leg's numbers are a measurement at all."""

    def test_one_canned_answer_stubs_the_whole_leg(self):
        mixed = [record(stubbed=True), record(stubbed=False)]
        self.assertTrue(scoreboard.describe_provenance(mixed)["stubbed"])

    def test_an_arm_that_never_says_leaves_it_unknown_rather_than_false(self):
        self.assertIsNone(scoreboard.describe_provenance([record()])["stubbed"])

    def test_a_leg_that_cost_exactly_zero_is_not_a_measurement(self):
        facts = scoreboard.describe_provenance([record(stubbed=False, cost_usd=0.0)])
        self.assertEqual(facts["cost_usd"], 0.0)
        self.assertFalse(facts["is_measured"])
        self.assertIn("the whole leg cost 0 USD", facts["not_measured_why"])

    def test_a_leg_that_cost_money_and_was_not_canned_is_a_measurement(self):
        facts = scoreboard.describe_provenance([record(stubbed=False, cost_usd=0.0031)])
        self.assertTrue(facts["is_measured"])
        self.assertEqual(facts["not_measured_why"], [])

    def test_an_unreported_cost_is_none_and_not_a_free_leg(self):
        self.assertIsNone(scoreboard.describe_provenance([record(stubbed=False)])["cost_usd"])

    def test_a_leg_nobody_priced_is_not_a_measurement_either(self):
        """Measured is a positive claim. This leg came back measured because both of its
        denials were absence triggered: nothing said it was canned, so it was not canned, and
        nothing said what it cost, so it did not cost nothing."""
        facts = scoreboard.describe_provenance([record(stubbed=False)])
        self.assertFalse(facts["is_measured"])
        self.assertEqual(facts["not_measured_why"], ["no arm reported what the leg cost"])

    def test_two_answering_models_in_one_leg_is_a_hard_stop(self):
        with self.assertRaises(HarnessError) as raised:
            scoreboard.describe_provenance([record(model="model-a"), record(model="model-b")])
        self.assertIn("more than one model", str(raised.exception))


class CannedLegScoreboard(unittest.TestCase):
    """The attack the registry could not refuse: a fully canned leg, written down."""

    def build(self, report):
        directory = Path(tempfile.mkdtemp())
        (directory / "judge.md").write_text("grade it")
        (directory / "questions.jsonl").write_text(
            "".join(json.dumps(one) + "\n" for one in QUESTIONS))
        arm = directory / "arm.py"
        arm.write_text("#!/usr/bin/env python3\nimport json\nimport sys\n"
                       + ARM_BODY.replace("REPORT", report))
        arm.chmod(arm.stat().st_mode | stat.S_IEXEC)
        (directory / "config.yaml").write_text(CONFIG)
        run_dir = directory / "runs"
        cfg = config.load(directory / "config.yaml")
        return run_dir, question.bench(cfg, run_dir, cfg.models)

    def saved(self, run_dir):
        return (run_dir / "claude-sonnet-5" / "scoreboard.json").read_text()

    def test_a_canned_leg_says_so_at_the_top_of_its_scoreboard(self):
        run_dir, board = self.build('{"stubbed": True, "cost_usd": 0.0}')
        self.assertIs(board["claude-sonnet-5"]["stubbed"], True)
        self.assertIn('"stubbed": true', self.saved(run_dir))
        self.assertIs(json.loads(self.saved(run_dir))["stubbed"], True)

    def test_the_marker_survives_onto_every_graded_record(self):
        _, board = self.build('{"stubbed": True, "cost_usd": 0.0}')
        self.assertEqual([one["stubbed"] for one in board["claude-sonnet-5"]["records"]],
                         [True, True])

    def test_a_canned_leg_reads_as_no_measurement_beside_its_accuracy(self):
        _, board = self.build('{"stubbed": True, "cost_usd": 0.0}')
        leg = board["claude-sonnet-5"]
        self.assertEqual(leg["accuracy"], 1.0)
        self.assertFalse(leg["is_measured"])
        self.assertIn("canned replies answered at least one question", leg["not_measured_why"])

    def test_the_run_wide_scoreboard_carries_it_too(self):
        run_dir, _ = self.build('{"stubbed": True, "cost_usd": 0.0}')
        board = json.loads((run_dir / "scoreboard.json").read_text())
        self.assertIs(board["claude-sonnet-5"]["stubbed"], True)

    def test_the_model_the_arm_reports_reaches_the_leg(self):
        _, board = self.build('{"stubbed": False, "model": "claude-sonnet-5", "cost_usd": 0.5}')
        leg = board["claude-sonnet-5"]
        self.assertEqual(leg["model"], "claude-sonnet-5")
        self.assertTrue(leg["is_measured"])

    def test_an_arm_that_reports_neither_leaves_both_unknown_and_nothing_measured(self):
        """The whole leg run by an arm that vouches for nothing. Every fact about it is
        unknown, and unknown is not a measurement: this is the leg that used to reach the
        registry under is_measured true with an empty list of reasons against it."""
        _, board = self.build('{}')
        leg = board["claude-sonnet-5"]
        self.assertIsNone(leg["stubbed"])
        self.assertIsNone(leg["model"])
        self.assertIsNone(leg["cost_usd"])
        self.assertFalse(leg["is_measured"])
        self.assertEqual(len(leg["not_measured_why"]), 2)


if __name__ == "__main__":
    unittest.main()
