"""The gates an eval passes before it may be run, and the controls one of them grades."""
import json
import shutil
from pathlib import Path

import pytest

from proofbench import cli, config, controls, engine, gates, judge
from proofbench.util import HarnessError

from .test_grader import CHECK, entry, write_config

DEMO = Path(__file__).resolve().parent.parent / "examples" / "question-demo"
CLASSES = "classes: [composition, lookup, unanswerable]\n"


@pytest.fixture
def demo(tmp_path, monkeypatch):
    """The offline question demo, copied so a test can edit it, with each question's class
    taken from its type and a judge that rules a prose answer right when it names the answer."""
    root = Path(shutil.copytree(DEMO, tmp_path / "eval"))
    questions = root / "questions" / "lineage.jsonl"
    labelled = [{**json.loads(line), "class": json.loads(line)["type"]}
                for line in questions.read_text().splitlines()]
    questions.write_text("".join(json.dumps(one) + "\n" for one in labelled))
    (root / "proofbench.question.yaml").write_text(
        CLASSES + (root / "proofbench.question.yaml").read_text())
    monkeypatch.setattr(judge, "grade_answer", lambda prompt, question, result, model, limit: (
        {"correct": int(all(name in result["answer"] for name in question["answer_names"]))}, 0.01))
    monkeypatch.chdir(tmp_path)
    return root / "proofbench.question.yaml"


def check(path, gate, tmp_path):
    return gates.check(config.load(path), gate, tmp_path / "runs" / gate)


def recorded(path, gate):
    return json.loads((path.parent / gates.STATE).read_text())[gate]


def test_an_eval_nobody_checked_is_refused_and_the_refusal_names_every_gate(demo):
    cfg = config.load(demo)
    assert set(gates.status(cfg).values()) == {"not run"}
    with pytest.raises(HarnessError, match=r"adapter \(not run\).*headroom \(not run\)"):
        gates.refuse_unchecked(cfg)


def test_a_passed_gate_goes_stale_when_what_it_covered_changes(demo, tmp_path):
    assert check(demo, "coverage", tmp_path)
    assert gates.status(config.load(demo))["coverage"] == "passed"
    questions = demo.parent / "questions" / "lineage.jsonl"
    questions.write_text(questions.read_text() + "\n")
    assert gates.status(config.load(demo))["coverage"] == "stale"


def test_a_declared_class_with_no_question_fails_coverage(demo, tmp_path):
    demo.write_text(demo.read_text().replace("unanswerable]", "unanswerable, ambiguous]"))
    assert not check(demo, "coverage", tmp_path)
    assert "['ambiguous']" in recorded(demo, "coverage")["detail"]


def test_an_eval_that_declares_no_classes_fails_coverage_and_says_why(demo, tmp_path):
    demo.write_text(demo.read_text().replace(CLASSES, ""))
    assert not check(demo, "coverage", tmp_path)
    assert "declares no `classes`" in recorded(demo, "coverage")["detail"]


def test_the_mechanical_controls_are_written_with_their_predictions(demo):
    cfg = config.load(demo)
    assert controls.build(cfg) == 10
    predictions = json.loads((controls.folder(cfg) / "predictions.json").read_text())
    assert predictions["LQ-0001/named"] == {"correct": [1, 1]}
    assert predictions["LQ-0003/nothing"] == {"correct": [1, 1]}
    assert predictions["LQ-0003/noise"] == {"correct": [0, 0]}
    named = json.loads((controls.folder(cfg) / "LQ-0001" / "named.json").read_text())
    assert (named["answer"], named["answer_ids"]) == ("Per Pettersson", [])


def test_building_again_keeps_a_control_written_by_hand(demo):
    cfg = config.load(demo)
    controls.build(cfg)
    predictions_file = controls.folder(cfg) / "predictions.json"
    by_hand = {**json.loads(predictions_file.read_text()), "LQ-0001/wrong-year": {"correct": [0, 0]}}
    predictions_file.write_text(json.dumps(by_hand))
    controls.build(cfg)
    assert "LQ-0001/wrong-year" in json.loads(predictions_file.read_text())


def test_the_controls_gate_passes_a_grader_that_scores_as_predicted(demo, tmp_path):
    controls.build(config.load(demo))
    assert check(demo, "controls", tmp_path)
    assert recorded(demo, "controls")["cost_usd"] == 0.04


def test_the_controls_gate_fails_a_judge_that_says_yes_to_everything(demo, tmp_path, monkeypatch):
    controls.build(config.load(demo))
    monkeypatch.setattr(judge, "grade_answer", lambda *args: ({"correct": 1}, 0.01))
    assert not check(demo, "controls", tmp_path)
    assert "LQ-0001/noise" in recorded(demo, "controls")["detail"]


def test_a_prediction_with_no_control_fails_the_gate(demo, tmp_path):
    cfg = config.load(demo)
    controls.build(cfg)
    (controls.folder(cfg) / "LQ-0002" / "named.json").unlink()
    assert not check(demo, "controls", tmp_path)
    assert "unpaired: ['LQ-0002/named']" in recorded(demo, "controls")["detail"]


def test_an_adapter_that_cannot_answer_fails_its_gate_with_the_reason(demo, tmp_path):
    assert check(demo, "adapter", tmp_path)
    (demo.parent / "arms" / "oracle-tier1.py").write_text("#!/bin/sh\nexit 3\n")
    assert not gates.check(config.load(demo), "adapter", tmp_path / "runs" / "again")
    assert "arm exited 3" in recorded(demo, "adapter")["detail"]


def test_headroom_fails_an_eval_the_strongest_model_scores_everything_on(demo, tmp_path, monkeypatch):
    assert check(demo, "headroom", tmp_path)
    assert "accuracy=0.667" in recorded(demo, "headroom")["detail"]
    monkeypatch.setattr(engine, "bench", lambda cfg, run_dir, models: {"stub": {"accuracy": 1.0}})
    assert not gates.check(config.load(demo), "headroom", tmp_path / "runs" / "again")


def run_cli(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["proofbench", *argv])
    cli.main()


def test_run_refuses_until_every_gate_passed_and_marks_what_it_ran_unchecked(demo, tmp_path,
                                                                             monkeypatch):
    with pytest.raises(SystemExit) as refused:
        run_cli(monkeypatch, "run", "--config", str(demo))
    assert refused.value.code == 1
    run_cli(monkeypatch, "run", "--config", str(demo), "--unchecked", "--run-id", "unchecked")
    board = json.loads((tmp_path / "runs" / "unchecked" / "scoreboard.json").read_text())
    assert board["stub"]["eval_checked"] is False
    run_cli(monkeypatch, "controls", "--config", str(demo))
    for gate in gates.GATES:
        run_cli(monkeypatch, "check", gate, "--config", str(demo), "--run-id", f"gate-{gate}")
    run_cli(monkeypatch, "run", "--config", str(demo), "--run-id", "checked")
    board = json.loads((tmp_path / "runs" / "checked" / "scoreboard.json").read_text())
    assert board["stub"]["eval_checked"] is True


def test_status_exits_nonzero_while_a_gate_is_open(demo, monkeypatch, capsys):
    with pytest.raises(SystemExit) as stopped:
        run_cli(monkeypatch, "status", "--config", str(demo))
    assert stopped.value.code == 1
    assert "coverage  not run" in capsys.readouterr().out


def test_a_judged_repo_task_gets_diff_controls_the_judge_must_score_as_predicted(repo, tmp_path,
                                                                                 monkeypatch):
    path = write_config(repo, entry(repo), "judge: default\n")
    cfg = config.load(path)
    assert controls.build(cfg) == 3
    monkeypatch.setattr(judge, "grade", lambda prompt, readme, answer, diff, *rest, **named: (
        {"recall": float("+x = 2" in diff)}, 0.05))
    assert gates.check(cfg, "controls", tmp_path / "gate")
    assert recorded(path, "controls")["cost_usd"] == 0.15


def test_a_command_graded_task_must_fail_at_the_start_and_pass_on_the_answer(repo, tmp_path):
    """The check here refuses to run twice in one clone, as a stale cache would make it."""
    once = f"test ! -e seen && touch seen && {CHECK}"
    path = write_config(repo, entry(repo, f', check: "{once}"'))
    cfg = config.load(path)
    assert controls.build(cfg) == 2
    assert gates.check(cfg, "controls", tmp_path / "gate")
    path.write_text(path.read_text().replace(once, "true"))
    assert not gates.check(config.load(path), "controls", tmp_path / "again")
    assert "fix/start" in recorded(path, "controls")["detail"]


def test_half_a_diff_keeps_the_first_half_of_its_hunks_under_their_headers():
    diff = ("diff --git a/one b/one\n--- a/one\n+++ b/one\n@@ -1 +1 @@\n-a\n+b\n@@ -9 +9 @@\n-c\n+d\n"
            "diff --git a/two b/two\n--- a/two\n+++ b/two\n@@ -1 +1 @@\n-e\n+f\n")
    assert controls._half(diff) == "diff --git a/one b/one\n--- a/one\n+++ b/one\n@@ -1 +1 @@\n-a\n+b\n"
    assert controls._half(diff.split("@@ -9")[0]) == ""
