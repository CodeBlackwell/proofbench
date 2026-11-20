"""Repeated trials: pass^k and pass@k, from the config key to the scoreboard a run writes.

One trial of a question says whether the arm can be right. It cannot say whether the arm is
right every time, and an arm that answers a question correctly two times in three scores the
same on a single run as one that never misses it. pass^k is the reliability reading and pass@k
the capability reading, and both are counted over the trials of each question.

Offline: the metrics are built from graded records, and the one bench that runs uses stub arms."""
import json
import stat
import tempfile
import unittest
from pathlib import Path

from proofbench import config, engine, question, scoreboard
from proofbench.util import HarnessError

from .stubs import read_question_from

FIXTURE = Path(__file__).resolve().parent.parent / "examples" / "question-demo"


def trials_of(question_id, grades, answerable=True):
    """One question's trials, graded in order: (1, 0, 0) is right once and wrong twice."""
    return [{"id": question_id, "trial": trial, "correct": correct, "graded_by": "exact",
             "abstained": not answerable, "answerable": answerable,
             "tokens_in": 100, "tokens_out": 10,
             "question": {"tier": 1, "hops": 1, "type": "lookup"}}
            for trial, correct in enumerate(grades, 1)]


def steady_and_shaky():
    """Two questions over three trials: one always right, one right once."""
    return trials_of("Q-steady", (1, 1, 1)) + trials_of("Q-shaky", (1, 0, 0))


class PassRates(unittest.TestCase):

    def setUp(self):
        self.leg = scoreboard.metrics(steady_and_shaky())

    def test_a_leg_counts_questions_and_trials_apart(self):
        self.assertEqual((self.leg["questions"], self.leg["trials"], self.leg["answerable"]),
                         (2, 3, 2))

    def test_pass_hat_k_falls_as_k_asks_for_more_agreement(self):
        self.assertEqual([self.leg[f"pass^{k}"] for k in (1, 2, 3)], [0.667, 0.5, 0.5])

    def test_pass_at_k_rises_as_k_allows_more_tries(self):
        self.assertEqual([self.leg[f"pass@{k}"] for k in (1, 2, 3)], [0.667, 0.833, 1.0])

    def test_both_start_at_the_per_trial_accuracy(self):
        self.assertEqual(self.leg["pass^1"], self.leg["accuracy"])
        self.assertEqual(self.leg["pass@1"], self.leg["accuracy"])

    def test_the_question_that_flipped_is_named(self):
        self.assertEqual(self.leg["unstable_questions"], ["Q-shaky"])

    def test_a_question_wrong_every_time_is_not_unstable(self):
        leg = scoreboard.metrics(trials_of("Q-lost", (0, 0, 0)))
        self.assertEqual(leg["unstable_questions"], [])
        self.assertEqual((leg["pass^3"], leg["pass@3"]), (0.0, 0.0))

    def test_one_trial_yields_only_k_of_one(self):
        leg = scoreboard.metrics(trials_of("Q-once", (1,)))
        self.assertEqual((leg["trials"], leg["pass^1"], leg["pass@1"]), (1, 1.0, 1.0))
        self.assertNotIn("pass^2", leg)

    def test_unequal_trial_counts_are_a_hard_stop(self):
        with self.assertRaises(HarnessError) as raised:
            scoreboard.metrics(trials_of("Q-a", (1, 1)) + trials_of("Q-b", (1,)))
        self.assertIn("unequal", str(raised.exception))

    def test_an_abstention_only_leg_carries_them_under_the_abstention_name(self):
        leg = scoreboard.metrics(trials_of("Q-absent", (1, 1, 0), answerable=False))
        self.assertEqual(leg["abstention_pass^3"], 0.0)
        self.assertEqual(leg["abstention_pass@3"], 1.0)
        self.assertNotIn("pass^3", leg)

    def test_the_grid_reads_a_pass_rate_like_any_other_metric(self):
        printed = scoreboard.grid(steady_and_shaky(), "tier", "hops", "pass^3").splitlines()
        self.assertEqual(printed[0], "pass^3 by tier x hops")
        self.assertEqual(printed[3].split("|")[1].split()[0], "0.5")

    def test_a_pass_rate_is_an_objective_the_gate_can_read(self):
        self.assertEqual(engine.objective_of(self.leg, "pass^3"), 0.5)


class TrialsConfig(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def load(self, body):
        root = Path(self.tmp.name)
        (root / "judge.md").write_text("grade it")
        (root / "questions.jsonl").write_text("{}\n")
        (root / "arm.py").write_text("")
        (root / "arm.py").chmod(0o755)
        (root / "config.yaml").write_text("models: [stub]\njudge: judge.md\nrunner: arm.py\n" + body)
        return config.load(root / "config.yaml")

    def test_trials_default_to_one(self):
        cfg = self.load("corpus:\n  - kind: question\n    file: questions.jsonl\n")
        self.assertEqual(cfg.trials, 1)

    def test_a_pass_objective_within_the_trials_loads(self):
        cfg = self.load("trials: 3\nobjective: pass^3\n"
                        "corpus:\n  - kind: question\n    file: questions.jsonl\n")
        self.assertEqual((cfg.trials, cfg.objective), (3, "pass^3"))

    def test_an_objective_beyond_the_trials_is_refused_before_the_run(self):
        with self.assertRaises(HarnessError) as raised:
            self.load("trials: 2\nobjective: pass@5\n"
                      "corpus:\n  - kind: question\n    file: questions.jsonl\n")
        self.assertIn("needs 5 trials", str(raised.exception))

    def test_no_trials_is_refused(self):
        with self.assertRaises(HarnessError):
            self.load("trials: 0\ncorpus:\n  - kind: question\n    file: questions.jsonl\n")

    def test_a_repo_corpus_refuses_trials(self):
        with self.assertRaises(HarnessError) as raised:
            self.load("trials: 3\ncorpus:\n  - name: primes\n    path: .\n    invoke: fix\n"
                      "    default_branch: buggy\n    answer_branch: fixed\n")
        self.assertIn("question corpus key", str(raised.exception))


class TrialsBench(unittest.TestCase):
    """The demo corpus asked three times by an arm that is right on its first call only."""

    ARM = (read_question_from(FIXTURE / "questions" / "lineage.jsonl") + "import pathlib\n"
           "seen = pathlib.Path(__file__).with_name('seen-' + question['id'])\n"
           "first = not seen.exists()\n"
           "seen.touch()\n"
           "right = first and question['answerable']\n"
           "print(json.dumps({'answer': '', 'answer_ids': question['answer'] if right else [],\n"
           "                  'abstained': not right, 'tokens_in': 100, 'tokens_out': 10,\n"
           "                  'stubbed': True}))\n")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        arm = root / "arm.py"
        arm.write_text("#!/usr/bin/env python3\nimport sys\n" + self.ARM)
        arm.chmod(arm.stat().st_mode | stat.S_IEXEC)
        (root / "judge.md").write_text("grade it")
        (root / "config.yaml").write_text(
            "models: [stub]\njudge: judge.md\nrunner: arm.py\ntrials: 3\nconcurrency: 1\n"
            f"objective: pass^3\ncorpus:\n  - kind: question\n    file: {FIXTURE}/questions/lineage.jsonl\n")
        self.cfg = config.load(root / "config.yaml")
        self.run_dir = root / "run"
        self.leg = question.bench(self.cfg, self.run_dir, self.cfg.models)["stub"]

    def test_every_question_is_asked_once_per_trial(self):
        self.assertEqual((self.leg["questions"], self.leg["trials"]), (3, 3))
        self.assertEqual(len(self.leg["records"]), 9)
        self.assertEqual(sorted({record["trial"] for record in self.leg["records"]}), [1, 2, 3])

    def test_each_trial_keeps_its_own_result_on_disk(self):
        saved = json.loads((self.run_dir / "stub" / "LQ-0001" / "trial-2" / "result.json").read_text())
        self.assertEqual((saved["grade"]["trial"], saved["grade"]["correct"]), (2, 0))

    def test_the_arm_that_was_right_once_passes_at_k_and_fails_hat_k(self):
        """Two answerable questions right on trial 1 only, one unanswerable abstained on always."""
        self.assertEqual((self.leg["pass^3"], self.leg["pass@3"]), (0.333, 1.0))
        self.assertEqual(self.leg["unstable_questions"], ["LQ-0001", "LQ-0002"])

    def test_the_saved_scoreboard_carries_the_whole_curve(self):
        saved = json.loads((self.run_dir / "scoreboard.json").read_text())["stub"]
        self.assertEqual([saved[f"pass^{k}"] for k in (1, 2, 3)], [0.556, 0.333, 0.333])

    def test_two_questions_sharing_an_id_are_refused(self):
        shared = Path(self.tmp.name) / "shared.jsonl"
        line = (FIXTURE / "questions" / "lineage.jsonl").read_text().splitlines()[0]
        shared.write_text(line + "\n" + line + "\n")
        self.cfg.corpus[0].path = shared
        with self.assertRaises(HarnessError) as raised:
            question.bench(self.cfg, self.run_dir / "again", self.cfg.models)
        self.assertIn("not unique", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
