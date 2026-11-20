"""The self-improving loop: what the synth is shown, and what the gate keeps.

`optimize` had no test, and it could not have passed one. It looked for the baseline's grades
one directory above where the baseline wrote them, so a repo corpus stopped on a missing folder,
and a question corpus writes no grade.json at all, so its synth was handed nothing to learn
from. The gate also kept any larger number, which for a token price is a regression.

The gate also scored a rewrite on the very questions it had been shown the answers to, so a
rewrite that only memorised them was kept. The corpus is now two files: the three demo questions
the synth learns from, and the same three under other ids, held out, that the gate scores on.

Offline: the arm is a stub whose answers depend on the subject file, and the synth is patched."""
import json
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from proofbench import config, engine, judge, optimize
from proofbench.util import HarnessError

from .stubs import read_question_from

FIXTURE = Path(__file__).resolve().parent.parent / "examples" / "question-demo"
ALL_THREE = "LQ-0001 LQ-0002 LQ-0003"          # every training question, and nothing held out
ONE_EACH = "LQ-0001 HQ-0001"                   # the starting subject: one right on each side
ALL_SIX = ALL_THREE + " HQ-0001 HQ-0002 HQ-0003"

# Right on a question exactly when the subject file names that question's id.
ARM = ("subject = open(sys.argv[sys.argv.index('--subject') + 1]).read()\n"
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
        train = (FIXTURE / "questions" / "lineage.jsonl").read_text()
        (self.root / "train.jsonl").write_text(train)
        (self.root / "held.jsonl").write_text(
            train.replace('"LQ-', '"HQ-').replace('"text": "', '"text": "Held out: '))
        (self.root / "key.jsonl").write_text(train + (self.root / "held.jsonl").read_text())
        arm.write_text("#!/usr/bin/env python3\n" + read_question_from(self.root / "key.jsonl") + ARM)
        arm.chmod(arm.stat().st_mode | stat.S_IEXEC)
        (self.root / "judge.md").write_text("grade it")
        (self.root / "synth.md").write_text("rewrite it")
        (self.root / "config.yaml").write_text(
            "models: [stub]\njudge: judge.md\nsynth: synth.md\nsubject: subject.md\nrunner: arm.py\n"
            f"runner_args: ['--subject', '{self.subject}']\nobjective: accuracy\nconcurrency: 1\n"
            "corpus:\n  - {kind: question, file: train.jsonl}\n"
            "  - {kind: question, file: held.jsonl, holdout: true}\n")

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

    def test_a_rewrite_that_scores_higher_on_the_held_out_questions_is_kept(self):
        kept, _ = self.run_loop(ONE_EACH, ALL_SIX)
        self.assertTrue(kept)
        self.assertEqual(self.subject.read_text(), ALL_SIX)
        saved = json.loads((self.root / "run" / "result.json").read_text())
        self.assertEqual((saved["baseline"], saved["improved"], saved["kept"]), (0.333, 1.0, True))
        self.assertEqual(saved["held_out"], ["held"])

    def test_a_rewrite_that_scores_lower_is_reverted(self):
        kept, _ = self.run_loop(ONE_EACH, "names no question")
        self.assertFalse(kept)
        self.assertEqual(self.subject.read_text(), ONE_EACH)

    def test_a_rewrite_that_only_memorised_the_training_answers_is_reverted(self):
        """It names every question the synth was shown and gets all of them right. The gate
        never asks those: on the held-out three it lost the one the old subject had."""
        kept, _ = self.run_loop(ONE_EACH, ALL_THREE)
        self.assertFalse(kept)
        self.assertEqual(self.subject.read_text(), ONE_EACH)

    def test_the_synth_is_never_shown_a_held_out_question(self):
        _, synth = self.run_loop(ONE_EACH, ALL_SIX)
        self.assertNotIn("Held out", synth.call_args.args[0])
        self.assertNotIn("--- HQ-", synth.call_args.args[0])

    def test_a_corpus_with_nothing_held_out_is_refused_before_the_baseline(self):
        path = self.root / "config.yaml"
        path.write_text(path.read_text().replace(", holdout: true", ""))
        with patch.object(engine, "bench", side_effect=AssertionError("the baseline ran")), \
                self.assertRaises(HarnessError) as raised:
            self.run_loop(ONE_EACH, ALL_SIX)
        self.assertIn("holdout", str(raised.exception))

    def test_a_question_on_both_sides_of_the_split_is_refused(self):
        (self.root / "held.jsonl").write_text((self.root / "train.jsonl").read_text())
        with self.assertRaises(HarnessError) as raised:
            self.run_loop(ONE_EACH, ALL_SIX)
        self.assertIn("not unique", str(raised.exception))

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

    def test_a_crash_during_the_re_run_puts_the_original_subject_back(self):
        real, calls = engine.bench, []

        def bench_then_interrupt(*args):
            calls.append(args)
            if len(calls) == 3:    # held-out baseline, training baseline, then the re-run
                raise KeyboardInterrupt
            return real(*args)
        with patch.object(engine, "bench", bench_then_interrupt), self.assertRaises(KeyboardInterrupt):
            self.run_loop(ONE_EACH, ALL_SIX)
        self.assertEqual(self.subject.read_text(), ONE_EACH)

    def test_a_candidate_that_leaves_the_objective_undefined_is_reverted(self):
        """Nothing right means no token price, which stops the run: the worst candidate of all
        must not be the one left in the subject file."""
        path = self.root / "config.yaml"
        path.write_text(path.read_text().replace("objective: accuracy", "objective: tokens_per_correct"))
        with self.assertRaises(HarnessError) as raised:
            self.run_loop(ONE_EACH, "names no question")
        self.assertIn("undefined", str(raised.exception))
        self.assertTrue((self.root / "run" / "subject.candidate").exists())
        self.assertEqual(self.subject.read_text(), ONE_EACH)


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


class RepoSplit(unittest.TestCase):

    def test_the_gate_scores_the_held_out_tasks_and_the_synth_reads_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text("find the bug")
            task = dict(path=root, invoke="fix", default_branch="buggy", answer_branch="fixed")
            cfg = config.Config(
                root=root, runner="claude", models=["weak"], judge_model="strong", synth_model="strong",
                objective="macro_recall", concurrency=1, max_turns=1, judge_prompt="grade",
                subject=root / "SKILL.md", synth_prompt="rewrite",
                corpus=[config.Task(name="learn", **task), config.Task(name="held", holdout=True, **task)])
            benched = []

            def fake_bench(part, run_dir, models):
                benched.append(([one.name for one in part.corpus], run_dir.name))
                for one in part.corpus:
                    (run_dir / "weak" / one.name).mkdir(parents=True)
                    (run_dir / "weak" / one.name / "grade.json").write_text(f'{{"task": "{one.name}"}}')
                return {"weak": {"macro_recall": 0.5}}
            rewrite = {"subject": "find the bug carefully", "changelog": ""}
            with patch.object(engine, "bench", fake_bench), \
                    patch.object(optimize, "claude_json", return_value=rewrite) as synth:
                optimize.optimize(cfg, root / "run")
        self.assertEqual(benched, [(["held"], "baseline-holdout"), (["learn"], "baseline"),
                                   (["held"], "improved")])
        self.assertIn('"task": "learn"', synth.call_args.args[0])
        self.assertNotIn('"task": "held"', synth.call_args.args[0])


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
