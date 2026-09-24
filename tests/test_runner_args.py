"""runner_args: the config's own argv for the arm, appended after --model MODEL.

proofbench invoked every arm with --model and nothing else, so an arm that has to be told which
frozen corpus to read exited 1 on the first question and no such config could run at all. These
cases pin the flags the whole way, from the yaml list to the process the runner starts.

unittest cases rather than bare pytest functions, so the suite runs under both `pytest tests`
and `python3 -m unittest`. Everything here is offline: the arms are stub executables.
"""
import json
import stat
import tempfile
import unittest
from pathlib import Path

from proofbench import config, question, runner
from proofbench.util import HarnessError

FIXTURE = Path(__file__).resolve().parent.parent / "examples" / "question-demo"
DEMO_QUESTION = FIXTURE / "proofbench.question.yaml"
DEMO_REPO = Path(__file__).resolve().parent.parent / "examples" / "proofbench.demo.yaml"

QUESTION = {"id": "LQ-0001", "text": "Who supervised Josephine Sundqvist?", "answer": [],
            "answer_names": [], "answerable": False, "tier": 1, "hops": 1, "type": "unanswerable"}

ECHO_ARGV = '''import json
print(json.dumps({"answer": " ".join(sys.argv[1:]), "answer_ids": [], "abstained": True,
                  "tokens_in": 100, "tokens_out": 10}))
'''

NEEDS_SNAPSHOT = '''import json
if "--snapshot" not in sys.argv:
    sys.stderr.write("usage: arm.py --model ID --snapshot HASH\\n")
    sys.exit(1)
print(json.dumps({"answer": "answered", "answer_ids": [], "abstained": True,
                  "tokens_in": 100, "tokens_out": 10}))
'''

SNAPSHOT = "3f9a2c1b8e"


def write_arm(directory, body):
    arm = Path(directory) / "arm.py"
    arm.write_text("#!/usr/bin/env python3\nimport sys\n" + body)
    arm.chmod(arm.stat().st_mode | stat.S_IEXEC)
    return arm


def write_config(directory, body, arm_body=NEEDS_SNAPSHOT):
    """A question config whose arm, judge prompt and question file all sit beside it."""
    write_arm(directory, arm_body)
    (Path(directory) / "judge.md").write_text("grade it")
    (Path(directory) / "questions.jsonl").write_text(json.dumps(QUESTION) + "\n")
    path = Path(directory) / "config.yaml"
    path.write_text("models: [stub]\njudge: judge.md\nrunner: arm.py\n"
                    "corpus:\n  - kind: question\n    file: questions.jsonl\n" + body)
    return path


class FromTheYaml(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_a_config_that_names_no_flags_passes_none(self):
        self.assertEqual(config.load(DEMO_QUESTION).runner_args, [])

    def test_the_repo_demo_passes_none_either(self):
        self.assertEqual(config.load(DEMO_REPO).runner_args, [])

    def test_the_list_reaches_the_config_in_file_order(self):
        path = write_config(self.tmp.name, f"runner_args: [--snapshot, {SNAPSHOT}, --cite]\n")
        self.assertEqual(config.load(path).runner_args, ["--snapshot", SNAPSHOT, "--cite"])

    def test_an_unquoted_number_is_a_hard_stop(self):
        path = write_config(self.tmp.name, "runner_args: [--k, 8]\n")
        with self.assertRaises(HarnessError) as raised:
            config.load(path)
        self.assertIn("list of strings", str(raised.exception))

    def test_a_bare_string_is_a_hard_stop(self):
        path = write_config(self.tmp.name, "runner_args: --snapshot\n")
        with self.assertRaises(HarnessError):
            config.load(path)

    def test_a_repo_task_cannot_carry_them(self):
        directory = Path(self.tmp.name)
        (directory / "judge.md").write_text("grade it")
        path = directory / "config.yaml"
        path.write_text(f"models: [stub]\njudge: judge.md\nrunner: claude\n"
                        f"runner_args: [--snapshot, {SNAPSHOT}]\n"
                        "corpus:\n  - name: primes\n    path: .\n    invoke: fix\n"
                        "    default_branch: buggy\n    answer_branch: fixed\n")
        with self.assertRaises(HarnessError) as raised:
            config.load(path)
        self.assertIn("nowhere to put", str(raised.exception))


class IntoTheArm(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "run.log"

    def test_the_flags_follow_model_in_the_argv(self):
        arm = write_arm(self.tmp.name, ECHO_ARGV)
        result = runner.ask(arm, "stub", QUESTION, self.log, ["--snapshot", SNAPSHOT, "--cite"])
        self.assertEqual(result["answer"], f"--model stub --snapshot {SNAPSHOT} --cite")

    def test_an_arm_that_needs_a_snapshot_cannot_run_without_one(self):
        arm = write_arm(self.tmp.name, NEEDS_SNAPSHOT)
        with self.assertRaises(HarnessError) as raised:
            runner.ask(arm, "stub", QUESTION, self.log)
        self.assertIn("exited 1", str(raised.exception))

    def test_the_same_arm_runs_once_the_config_pins_it(self):
        arm = write_arm(self.tmp.name, NEEDS_SNAPSHOT)
        result = runner.ask(arm, "stub", QUESTION, self.log, ["--snapshot", SNAPSHOT])
        self.assertEqual(result["answer"], "answered")


class ThroughTheLeg(unittest.TestCase):
    """The whole question leg, which is where the blocking defect showed: one arm requiring a
    flag only the config can supply, driven by bench the way a real run drives it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "runs"

    def bench(self, body):
        cfg = config.load(write_config(self.tmp.name, body))
        return question.bench(cfg, self.run_dir, cfg.models)["stub"]

    def test_the_leg_runs_when_the_config_pins_the_snapshot(self):
        """The one fixture question is unanswerable, so this leg can report an abstention and
        nothing else. It used to report that same count under `correct`, beside an accuracy."""
        leg = self.bench(f"runner_args: [--snapshot, {SNAPSHOT}]\n")
        self.assertEqual(leg["questions"], 1)
        self.assertEqual(leg["correct_abstentions"], 1)
        self.assertNotIn("accuracy", leg)

    def test_the_leg_dies_loudly_when_it_does_not(self):
        with self.assertRaises(HarnessError) as raised:
            self.bench("")
        self.assertIn("exited 1", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
