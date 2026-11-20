"""The question task kind end to end, and the grading rules that decide a correct answer.

Written as unittest cases rather than bare pytest functions so the suite runs under both
`pytest tests` and `python3 -m unittest`, with no plugin and no fixture file. Everything here
is offline: the arm is a stub executable and the judge is never reached unless a test patches
it in on purpose."""
import json
import os
import stat
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

from proofbench import config, judge, question, runner
from proofbench.util import HarnessError

FIXTURE = Path(__file__).resolve().parent.parent / "examples" / "question-demo"
CONFIG = FIXTURE / "proofbench.question.yaml"

ANSWERABLE = {"id": "LQ-0001", "text": "Who supervised the advisor of Josephine Sundqvist?",
              "answer": ["diva:Pettersson, Per"], "answer_names": ["Per Pettersson"],
              "answerable": True, "tier": 1, "hops": 2, "type": "composition"}
UNANSWERABLE = {**ANSWERABLE, "id": "LQ-0003", "answer": [], "answer_names": [],
                "answerable": False}


def result(answer_ids, abstained=False, answer=""):
    return {"answer": answer, "answer_ids": answer_ids, "abstained": abstained,
            "tokens_in": 100, "tokens_out": 10}


def write_arm(directory, body):
    arm = Path(directory) / "arm.py"
    arm.write_text("#!/usr/bin/env python3\nimport sys\n" + body)
    arm.chmod(arm.stat().st_mode | stat.S_IEXEC)
    return arm


class QuestionBench(unittest.TestCase):
    """Accepts 2: three questions, one of them unanswerable, to known numbers."""

    def setUp(self):
        self.cfg = config.load(CONFIG)
        self.run_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.run_dir.cleanup)
        self.leg = question.bench(self.cfg, Path(self.run_dir.name), self.cfg.models)["stub"]

    def test_headline_numbers_are_the_fixture_numbers(self):
        self.assertEqual(self.leg["questions"], 3)
        self.assertEqual(self.leg["correct"], 2)
        self.assertEqual(self.leg["accuracy"], 0.667)

    def test_abstention_is_split_by_answerability(self):
        self.assertEqual(self.leg["non_abstention_rate_answerable"], 0.5)
        self.assertEqual(self.leg["abstention_correct_unanswerable"], 1.0)

    def test_tokens_and_the_price_of_one_correct_answer(self):
        self.assertEqual(self.leg["tokens_total"], 330)
        self.assertEqual(self.leg["tokens_per_correct"], 165.0)

    def test_each_question_records_how_it_was_graded(self):
        graded = {record["id"]: record["graded_by"] for record in self.leg["records"]}
        self.assertEqual(graded, {"LQ-0001": "exact", "LQ-0002": "abstention",
                                  "LQ-0003": "abstention"})

    def test_the_demo_arm_says_it_is_canned(self):
        self.assertIs(self.leg["stubbed"], True)
        self.assertFalse(self.leg["is_measured"])

    def test_the_leg_scoreboard_is_written(self):
        saved = json.loads((Path(self.run_dir.name) / "stub" / "scoreboard.json").read_text())
        self.assertEqual(saved["accuracy"], 0.667)


class Grading(unittest.TestCase):

    def setUp(self):
        self.cfg = config.load(CONFIG)

    def grade(self, question_line, arm_result):
        return question.grade_one(self.cfg, question_line, arm_result, "judge-model")

    def test_exact_id_match_never_reaches_the_judge(self):
        with patch.object(judge, "grade_answer", side_effect=AssertionError("judge called")):
            self.assertEqual(self.grade(ANSWERABLE, result(["diva:Pettersson, Per"])),
                             {"correct": 1, "graded_by": "exact"})

    def test_ids_match_case_and_whitespace_insensitively(self):
        with patch.object(judge, "grade_answer", side_effect=AssertionError("judge called")):
            self.assertEqual(self.grade(ANSWERABLE, result(["  DIVA:Pettersson,  Per "]))["correct"], 1)

    def test_ids_match_across_unicode_forms(self):
        """The DiVA snapshot holds one supervisor, Gutierrez-de-Teran, under four spellings.
        Two of them differ only in Unicode form: they print identically, and an answer in the
        one the arm read used to miss the answer key written in the other and fall to the judge
        as though they named two people."""
        composed = unicodedata.normalize("NFC", "diva:Gutiérrez-de-Terán, Hugo")
        decomposed = unicodedata.normalize("NFD", composed)
        self.assertNotEqual(composed.encode(), decomposed.encode())
        with patch.object(judge, "grade_answer", side_effect=AssertionError("judge called")):
            graded = self.grade({**ANSWERABLE, "answer": [composed]}, result([decomposed]))
        self.assertEqual(graded, {"correct": 1, "graded_by": "exact"})

    def test_the_other_two_spellings_stay_different_ids(self):
        """NFC folds the form, never the letters: spelling the diacritics or the hyphens away
        would merge names the snapshot deliberately keeps apart."""
        hyphenated = unicodedata.normalize("NFC", "diva:Gutiérrez-de-Terán, Hugo")
        for spelling in ("diva:Gutierrez de Teran, Hugo", "diva:Gutiérrez de Terán, Hugo"):
            self.assertNotEqual(question.normalise(spelling), question.normalise(hyphenated))

    def test_prose_answer_goes_to_the_judge(self):
        verdict = {"correct": 1, "why": "same person, given name written out"}
        with patch.object(judge, "grade_answer", return_value=verdict) as judged:
            graded = self.grade(ANSWERABLE, result([], answer="Per Pettersson"))
        self.assertEqual(graded["correct"], 1)
        self.assertEqual(graded["graded_by"], "judge")
        self.assertEqual(judged.call_count, 1)

    def test_abstention_is_correct_only_when_the_question_is_not_answerable(self):
        self.assertEqual(self.grade(UNANSWERABLE, result([], abstained=True))["correct"], 1)
        self.assertEqual(self.grade(ANSWERABLE, result([], abstained=True))["correct"], 0)

    def test_answering_an_unanswerable_question_is_wrong(self):
        with patch.object(judge, "grade_answer", side_effect=AssertionError("judge called")):
            graded = self.grade(UNANSWERABLE, result(["diva:Someone, Made Up"]))
        self.assertEqual(graded, {"correct": 0, "graded_by": "abstention"})


class FailLoud(unittest.TestCase):
    """Accepts 4: an empty, non numeric or non binary grade is a hard stop, never a zero."""

    def setUp(self):
        self.cfg = config.load(CONFIG)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "run.log"

    def test_a_non_binary_verdict_is_fatal(self):
        with patch.object(judge, "claude_json", return_value={"correct": 0.5}):
            with self.assertRaises(HarnessError):
                judge.grade_answer("prompt", ANSWERABLE, result([]), "judge-model")

    def test_a_verdict_with_no_correct_field_is_fatal(self):
        with patch.object(judge, "claude_json", return_value={"why": "it narrated"}):
            with self.assertRaises(HarnessError):
                judge.grade_answer("prompt", ANSWERABLE, result([]), "judge-model")

    def test_an_arm_result_without_token_counts_is_fatal(self):
        arm = write_arm(self.tmp.name,
                        'print(\'{"answer": "x", "answer_ids": [], "abstained": true}\')\n')
        with self.assertRaises(HarnessError) as raised:
            runner.ask(arm, "stub", ANSWERABLE, self.log)
        self.assertIn("tokens_in", str(raised.exception))

    def test_an_arm_is_handed_the_question_and_never_its_answer_key(self):
        """This arm answers with whatever it was handed, so the test reads the harness's stdin."""
        arm = write_arm(self.tmp.name,
                        'import json\nhanded = sys.stdin.read()\n'
                        'print(json.dumps({"answer": handed, "answer_ids": [], "abstained": True,'
                        ' "tokens_in": 1, "tokens_out": 1}))\n')
        handed = json.loads(runner.ask(arm, "stub", ANSWERABLE, self.log)["answer"])
        self.assertEqual(handed, {"id": ANSWERABLE["id"], "text": ANSWERABLE["text"]})

    def test_an_arm_that_prints_no_object_is_fatal(self):
        arm = write_arm(self.tmp.name, 'print("I could not answer that")\n')
        with self.assertRaises(HarnessError):
            runner.ask(arm, "stub", ANSWERABLE, self.log)

    def test_an_arm_that_exits_nonzero_is_fatal(self):
        arm = write_arm(self.tmp.name, 'sys.stderr.write("snapshot missing\\n")\nsys.exit(3)\n')
        with self.assertRaises(HarnessError) as raised:
            runner.ask(arm, "stub", ANSWERABLE, self.log)
        self.assertIn("exited 3", str(raised.exception))

    def test_an_empty_question_file_is_fatal(self):
        empty = Path(self.tmp.name) / "empty.jsonl"
        empty.write_text("\n")
        with self.assertRaises(HarnessError):
            question.load(empty)


class ClaudeUsage(unittest.TestCase):
    """The built in claude runner reads usage from the CLI envelope, not just cost."""

    def test_usage_tokens_come_off_the_envelope(self):
        envelope = json.dumps({"total_cost_usd": 0.03, "num_turns": 4,
                               "usage": {"input_tokens": 812, "output_tokens": 47}})
        self.assertEqual(runner._claude_meta(envelope),
                         {"cost_usd": 0.03, "turns": 4, "tokens_in": 812, "tokens_out": 47})

    def test_a_malformed_envelope_yields_no_meta_and_does_not_raise(self):
        self.assertEqual(runner._claude_meta("not an envelope"),
                         {"cost_usd": None, "turns": None, "tokens_in": None, "tokens_out": None})


if __name__ == "__main__":
    unittest.main()
