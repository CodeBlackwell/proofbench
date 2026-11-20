"""The self-improving loop: what the synth is shown, and what the gate keeps.

`optimize` had no test, and it could not have passed one. It looked for the baseline's grades
one directory above where the baseline wrote them, so a repo corpus stopped on a missing folder,
and a question corpus writes no grade.json at all, so its synth was handed nothing to learn
from. The gate also kept any larger number, which for a token price is a regression.

Offline: the arm is a stub whose answers depend on the subject file, and the synth is patched."""
import json
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from proofbench import config, judge, optimize
from proofbench.util import HarnessError

FIXTURE = Path(__file__).resolve().parent.parent / "examples" / "question-demo"
ALL_THREE = "LQ-0001 LQ-0002 LQ-0003"

# Right on a question exactly when the subject file names that question's id.
ARM = ("import json\n"
       "subject = open(sys.argv[sys.argv.index('--subject') + 1]).read()\n"
       "question = json.loads(sys.stdin.read())\n"
       "wrong = {'answer': 'someone else', 'answer_ids': ['diva:Nobody, At All'], 'abstained': False}\n"
       "right = {'answer': '', 'answer_ids': question['answer'], 'abstained': not question['answerable']}\n"
       "answer = right if question['id'] in subject else wrong\n"
       "print(json.dumps({**answer, 'tokens_in': 100, 'tokens_out': 10, 'stubbed': True}))\n")


class QuestionLoop(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.subject = self.root / "subject.md"
        arm = self.root / "arm.py"
        arm.write_text("#!/usr/bin/env python3\nimport sys\n" + ARM)
        arm.chmod(arm.stat().st_mode | stat.S_IEXEC)
        (self.root / "judge.md").write_text("grade it")
        (self.root / "synth.md").write_text("rewrite it")
        (self.root / "config.yaml").write_text(
            "models: [stub]\njudge: judge.md\nsynth: synth.md\nsubject: subject.md\nrunner: arm.py\n"
            f"runner_args: ['--subject', '{self.subject}']\nobjective: accuracy\nconcurrency: 1\n"
            f"corpus:\n  - kind: question\n    file: {FIXTURE}/questions/lineage.jsonl\n")

    def run_loop(self, subject_before, candidate):
        """Run optimize from a starting subject, with the synth returning `candidate`."""
        self.subject.write_text(subject_before)
        cfg = config.load(self.root / "config.yaml")
        wrong = {"correct": 0, "why": "names someone else"}
        rewrite = {"subject": candidate, "changelog": "- changed"}
        with patch.object(judge, "grade_answer", return_value=wrong), \
                patch.object(optimize, "claude_json", return_value=rewrite) as synth:
            kept = optimize.optimize(cfg, self.root / "run")
        return kept, synth

    def test_a_rewrite_that_scores_higher_is_kept(self):
        kept, _ = self.run_loop("LQ-0001", ALL_THREE)
        self.assertTrue(kept)
        self.assertEqual(self.subject.read_text(), ALL_THREE)
        saved = json.loads((self.root / "run" / "result.json").read_text())
        self.assertEqual((saved["baseline"], saved["improved"], saved["kept"]), (0.333, 1.0, True))

    def test_a_rewrite_that_scores_lower_is_reverted(self):
        kept, _ = self.run_loop("LQ-0001", "names no question")
        self.assertFalse(kept)
        self.assertEqual(self.subject.read_text(), "LQ-0001")

    def test_the_synth_is_shown_the_questions_the_arm_missed(self):
        _, synth = self.run_loop("LQ-0001", ALL_THREE)
        prompt = synth.call_args.args[0]
        self.assertIn("--- LQ-0002 ---", prompt)
        self.assertIn("Who supervised Mikko Korhonen?", prompt)
        self.assertIn("diva:Nobody, At All", prompt)          # what the arm answered
        self.assertIn("lutpub:Kalviainen, Heikki", prompt)    # what was expected

    def test_a_question_answered_right_is_left_out(self):
        _, synth = self.run_loop("LQ-0001", ALL_THREE)
        self.assertNotIn("--- LQ-0001 ---", synth.call_args.args[0])

    def test_a_corpus_private_field_never_reaches_the_synth(self):
        _, synth = self.run_loop("names no question", ALL_THREE)
        self.assertNotIn("urn:nbn:se:uu:diva-331085", synth.call_args.args[0])   # LQ-0001's evidence

    def test_a_baseline_with_no_miss_is_a_hard_stop_before_the_synth(self):
        with self.assertRaises(HarnessError) as raised:
            self.run_loop(ALL_THREE, "anything")
        self.assertIn("no grades to learn from", str(raised.exception))
        self.assertEqual(self.subject.read_text(), ALL_THREE)


class RepoGrades(unittest.TestCase):

    def test_the_synth_reads_the_grades_where_the_baseline_wrote_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            task = run_dir / "baseline" / "haiku" / "primes"
            task.mkdir(parents=True)
            (task / "grade.json").write_text('{"task": "primes", "recall": 0.5}')
            subject = run_dir / "SKILL.md"
            subject.write_text("find the bug")
            cfg = SimpleNamespace(kind="repo", synth_prompt="rewrite it", subject=subject, synth_model="opus")
            rewrite = {"subject": "find the bug carefully", "changelog": ""}
            with patch.object(optimize, "claude_json", return_value=rewrite) as synth:
                optimize._synth(cfg, run_dir, "haiku", leg=None)
        self.assertIn('--- primes ---\n{"task": "primes", "recall": 0.5}', synth.call_args.args[0])


class Gate(unittest.TestCase):

    def test_a_higher_rate_is_kept_and_a_lower_one_is_not(self):
        self.assertTrue(optimize._did_not_regress("pass^3", 0.4, 0.6))
        self.assertFalse(optimize._did_not_regress("pass^3", 0.6, 0.4))

    def test_a_lower_token_price_is_kept_and_a_higher_one_is_not(self):
        self.assertTrue(optimize._did_not_regress("tokens_per_correct", 800.0, 600.0))
        self.assertFalse(optimize._did_not_regress("tokens_per_correct", 600.0, 800.0))

    def test_an_unchanged_score_is_kept(self):
        self.assertTrue(optimize._did_not_regress("macro_recall", 0.5, 0.5))
        self.assertTrue(optimize._did_not_regress("tokens_per_correct", 700.0, 700.0))


if __name__ == "__main__":
    unittest.main()
