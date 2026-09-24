"""The question scoreboard: the metrics, the grouping, and the grid the study reads.

The grid is the point of the grouping: fifteen cells, tier crossed with hop depth, every one
of them computed from the per question records, so a saved scoreboard regroups by any
question field without re-running an arm."""
import tempfile
import unittest
from pathlib import Path

from proofbench import config, engine, scoreboard
from proofbench.util import HarnessError

FIXTURE = Path(__file__).resolve().parent.parent / "examples" / "question-demo"
CONFIG = FIXTURE / "proofbench.question.yaml"
DEMO = Path(__file__).resolve().parent.parent / "examples" / "proofbench.demo.yaml"

TIERS = (1, 2, 3)
DEPTHS = (1, 2, 3, 5, 7)


def record(correct, answerable=True, abstained=False, tier=1, hops=1, kind="lookup"):
    return {"id": f"LQ-{tier}{hops}", "correct": correct, "graded_by": "exact",
            "abstained": abstained, "answerable": answerable,
            "tokens_in": 100, "tokens_out": 10,
            "question": {"tier": tier, "hops": hops, "type": kind}}


def full_grid_records():
    """One answered question per cell: correct wherever hop depth is at most the tier."""
    return [record(int(hops <= tier), tier=tier, hops=hops)
            for tier in TIERS for hops in DEPTHS]


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


class Grouping(unittest.TestCase):

    def test_group_by_any_question_field(self):
        records = [record(1, kind="lookup"), record(0, kind="aggregation")]
        cells = scoreboard.group(records, ("type",))
        self.assertEqual(cells[("lookup",)]["accuracy"], 1.0)
        self.assertEqual(cells[("aggregation",)]["accuracy"], 0.0)

    def test_group_by_a_field_no_question_carries_is_a_hard_stop(self):
        with self.assertRaises(KeyError):
            scoreboard.group([record(1)], ("subject",))

    def test_the_grid_has_fifteen_cells(self):
        cells = scoreboard.group(full_grid_records(), ("tier", "hops"))
        self.assertEqual(len(cells), 15)
        self.assertEqual(cells[(3, 3)]["accuracy"], 1.0)
        self.assertEqual(cells[(1, 7)]["accuracy"], 0.0)

    def test_the_grid_prints_three_rows_of_five_depths_under_a_named_metric(self):
        printed = scoreboard.grid(full_grid_records(), "tier", "hops", "accuracy").splitlines()
        self.assertEqual(len(printed), 7)          # title, header, rule, three tiers, legend
        self.assertEqual(printed[0], "accuracy by tier x hops")
        for depth in DEPTHS:
            self.assertIn(f"hops={depth}", printed[1])
        self.assertEqual(printed[3].split("|")[1].split(), ["1.0", "0.0", "0.0", "0.0", "0.0"])


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
