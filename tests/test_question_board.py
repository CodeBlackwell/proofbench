"""The question scoreboard: the metrics, and the config that asks for them."""
import itertools
import tempfile
import unittest
from pathlib import Path

from proofbench import config, engine, scoreboard
from proofbench.util import HarnessError

FIXTURE = Path(__file__).resolve().parent.parent / "examples" / "question-demo"
CONFIG = FIXTURE / "proofbench.question.yaml"
DEMO = Path(__file__).resolve().parent.parent / "examples" / "proofbench.demo.yaml"

# Records sharing an id are trials of one question, so every record here takes its own.
SERIAL = itertools.count(1)


def record(correct, answerable=True, abstained=False):
    return {"id": f"LQ-{next(SERIAL):04d}", "correct": correct, "graded_by": "exact",
            "abstained": abstained, "answerable": answerable,
            "tokens_in": 100, "tokens_out": 10,
            "question": {"type": "lookup"}}


class Metrics(unittest.TestCase):

    def test_accuracy_and_token_price(self):
        numbers = scoreboard.metrics([record(1), record(1), record(0)])
        self.assertEqual(numbers["accuracy"], 0.667)
        self.assertEqual(numbers["tokens_total"], 330)
        self.assertEqual(numbers["tokens_per_correct"], 165.0)

    def test_abstention_is_reported_separately_per_answerability(self):
        records = [record(1, abstained=False),
                   record(0, abstained=True),
                   record(1, answerable=False, abstained=True),
                   record(0, answerable=False, abstained=False)]
        numbers = scoreboard.metrics(records)
        self.assertEqual(numbers["non_abstention_rate_answerable"], 0.5)
        self.assertEqual(numbers["abstention_correct_unanswerable"], 0.5)

    def test_an_all_answerable_set_has_no_unanswerable_rate(self):
        self.assertIsNone(scoreboard.metrics([record(1)])["abstention_correct_unanswerable"])

    def test_every_leg_says_how_many_of_its_questions_were_answerable(self):
        numbers = scoreboard.metrics([record(1), record(1, answerable=False, abstained=True)])
        self.assertEqual((numbers["answerable"], numbers["unanswerable"]), (1, 1))

    def test_nothing_correct_gives_no_token_price_rather_than_zero(self):
        numbers = scoreboard.metrics([record(0), record(0)])
        self.assertEqual(numbers["accuracy"], 0.0)
        self.assertIsNone(numbers["tokens_per_correct"])

    def test_an_undefined_objective_is_a_hard_stop(self):
        leg = scoreboard.metrics([record(0)])
        with self.assertRaises(HarnessError):
            engine.objective_of(leg, "tokens_per_correct")


class QuestionConfig(unittest.TestCase):

    def test_the_question_corpus_loads_with_its_arm_resolved(self):
        cfg = config.load(CONFIG)
        self.assertEqual(cfg.kind, "question")
        self.assertEqual(cfg.objective, "tokens_per_correct")
        self.assertEqual([task.name for task in cfg.corpus], ["lineage"])
        self.assertTrue(Path(cfg.runner).is_absolute())
        self.assertTrue(Path(cfg.runner).is_file())

    def test_the_repo_corpus_is_untouched(self):
        cfg = config.load(DEMO)
        self.assertEqual(cfg.kind, "repo")
        self.assertEqual(cfg.runner, "claude")
        self.assertEqual([task.name for task in cfg.corpus], ["primes", "ranges"])
        self.assertEqual(cfg.corpus[0].default_branch, "buggy")


class BadConfig(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, body):
        path = Path(self.tmp.name) / "config.yaml"
        (Path(self.tmp.name) / "judge.md").write_text("grade it")
        (Path(self.tmp.name) / "questions.jsonl").write_text("{}\n")
        path.write_text("models: [stub]\njudge: judge.md\n" + body)
        return path

    def test_a_question_corpus_refuses_the_builtin_claude_runner(self):
        path = self.write("runner: claude\ncorpus:\n  - kind: question\n    file: questions.jsonl\n")
        with self.assertRaises(HarnessError) as raised:
            config.load(path)
        self.assertIn("executable runner", str(raised.exception))

    def test_a_missing_arm_is_named(self):
        path = self.write("runner: arms/gone.py\ncorpus:\n"
                          "  - kind: question\n    file: questions.jsonl\n")
        with self.assertRaises(HarnessError) as raised:
            config.load(path)
        self.assertIn("runner not found", str(raised.exception))

    def test_a_missing_question_file_is_named(self):
        path = self.write("runner: arms/gone.py\ncorpus:\n"
                          "  - kind: question\n    file: nowhere.jsonl\n")
        with self.assertRaises(HarnessError) as raised:
            config.load(path)
        self.assertIn("question file not found", str(raised.exception))

    def test_a_corpus_cannot_mix_kinds(self):
        path = self.write("runner: arms/gone.py\ncorpus:\n"
                          "  - kind: question\n    file: questions.jsonl\n"
                          "  - name: primes\n    path: .\n    invoke: fix\n"
                          "    default_branch: buggy\n    answer_branch: fixed\n")
        with self.assertRaises(HarnessError) as raised:
            config.load(path)
        self.assertIn("mixes task kinds", str(raised.exception))

    def test_an_unknown_kind_is_named(self):
        path = self.write("runner: arms/gone.py\ncorpus:\n  - kind: essay\n    file: questions.jsonl\n")
        with self.assertRaises(HarnessError) as raised:
            config.load(path)
        self.assertIn("unknown corpus kind", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
