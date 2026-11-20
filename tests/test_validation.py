"""What is refused before a run is paid for: a config, a question file or an arm reply that
could only fail later, or worse, be read as something it is not.

Each of these used to surface after the arms and the judge had already been spent, as a raw
traceback or as a quietly wrong default: `models: haiku` ran five legs named h, a, i, k and u,
and a misspelt `judge_model` left the weak model grading itself."""
import json
import stat
import subprocess

import pytest

from proofbench import capture, cli, config, optimize, question, runner, util
from proofbench.util import HarnessError

from .conftest import git

QUESTION = {"id": "Q1", "text": "Who?", "answer": ["a1"], "answerable": True, "tier": 1, "hops": 1}
RESULT = {"answer_ids": [], "abstained": True, "tokens_in": 1, "tokens_out": 1}
BASE = {"models": "[stub]", "judge": "judge.md", "runner": "arm.py",
        "corpus": "\n  - {kind: question, file: questions.jsonl}"}


REPO_ENTRY = "\n  - {name: primes, path: ., invoke: fix, default_branch: buggy, answer_branch: fixed"


def write_arm(directory, reply=RESULT):
    arm = directory / "arm.py"
    arm.write_text(f"#!/usr/bin/env python3\nprint({json.dumps(json.dumps(reply))})\n")
    arm.chmod(arm.stat().st_mode | stat.S_IEXEC)
    return arm


def load(directory, questions=(QUESTION,), **keys):
    """A question config beside its arm, judge prompt and question file. A key set to None is
    left out of the config."""
    write_arm(directory)
    (directory / "judge.md").write_text("grade it")
    (directory / "questions.jsonl").write_text("".join(json.dumps(one) + "\n" for one in questions))
    body = {**BASE, **keys}
    (directory / "config.yaml").write_text(
        "".join(f"{key}: {value}\n" for key, value in body.items() if value is not None))
    return config.load(directory / "config.yaml")


# ---- the config

@pytest.mark.parametrize("keys, says", [
    ({"models": "haiku"}, "list of model names"),
    ({"models": "[]"}, "list of model names"),
    ({"judge_modle": "opus"}, "judge_modle"),
    ({"concurrency": "0"}, "concurrency"),
    ({"judge": "missing.md"}, "not found"),
    ({"subject": "missing.md", "synth": "judge.md"}, "not found"),
    ({"synth": "missing.md"}, "not found"),
    ({"objective": "macro_recall"}, "objective"),
    ({"objective": "tokens_total"}, "objective"),
    ({"timeout_minutes": "0"}, "timeout_minutes"),
    ({"corpus": "\n  - {kind: question}"}, "file"),
    ({"corpus": "\n  - {name: primes, path: .}"}, "invoke"),
    ({"corpus": REPO_ENTRY + ", ignore: dist}"}, "ignore"),
    ({"corpus": REPO_ENTRY + ", hold_out: true}"}, "hold_out"),
    ({"corpus": "\n  - {kind: question, file: questions.jsonl, holdout: yes please}"}, "holdout"),
])
def test_a_config_that_could_only_fail_later_is_refused_at_load(tmp_path, keys, says):
    with pytest.raises(HarnessError, match=says):
        load(tmp_path, **keys)


def test_a_config_that_is_not_a_mapping_is_refused(tmp_path):
    (tmp_path / "config.yaml").write_text("- models\n- corpus\n")
    with pytest.raises(HarnessError, match="mapping"):
        config.load(tmp_path / "config.yaml")


def test_a_runner_that_cannot_be_executed_is_refused_at_load(tmp_path):
    arm = write_arm(tmp_path)
    (tmp_path / "judge.md").write_text("grade it")
    (tmp_path / "questions.jsonl").write_text(json.dumps(QUESTION) + "\n")
    (tmp_path / "config.yaml").write_text("".join(f"{key}: {value}\n" for key, value in BASE.items()))
    arm.chmod(0o644)
    with pytest.raises(HarnessError, match="executable"):
        config.load(tmp_path / "config.yaml")


def test_a_question_config_may_leave_the_objective_out_and_still_run(tmp_path):
    assert load(tmp_path).objective is None


def test_optimize_without_an_objective_stops_before_the_baseline(tmp_path, monkeypatch):
    (tmp_path / "subject.md").write_text("subject")
    cfg = load(tmp_path, subject="subject.md", synth="judge.md")
    monkeypatch.setattr(optimize.engine, "bench", lambda *args: pytest.fail("the baseline ran"))
    with pytest.raises(HarnessError, match="objective"):
        optimize.optimize(cfg, tmp_path / "run")


# ---- the question file

@pytest.mark.parametrize("change", [
    {"answerable": None}, {"text": None}, {"answer": "a1"}, {"id": 7}, {"tier": None}, {"hops": None},
])
def test_a_question_missing_a_field_the_grade_reads_is_refused_at_load(tmp_path, change):
    path = tmp_path / "questions.jsonl"
    record = {key: value for key, value in {**QUESTION, **change}.items() if value is not None}
    path.write_text(json.dumps(QUESTION) + "\n" + json.dumps(record) + "\n")
    with pytest.raises(HarnessError, match="questions.jsonl:2"):
        question.load(path)


def test_a_line_that_is_not_json_is_refused_with_its_line_number(tmp_path):
    path = tmp_path / "questions.jsonl"
    path.write_text(json.dumps(QUESTION) + "\n{not json\n")
    with pytest.raises(HarnessError, match="questions.jsonl:2"):
        question.load(path)


def test_a_question_off_the_grid_is_refused_before_any_arm_is_asked(tmp_path, monkeypatch):
    cfg = load(tmp_path, questions=[{**QUESTION, "hops": 4}])
    monkeypatch.setattr(runner, "ask", lambda *args, **kwargs: pytest.fail("an arm was asked"))
    with pytest.raises(HarnessError, match="stratification"):
        question.bench(cfg, tmp_path / "run", cfg.models)


# ---- the arm's reply

@pytest.mark.parametrize("change", [
    {"abstained": "false"}, {"tokens_in": None}, {"tokens_out": "12"}, {"answer_ids": "a1"},
])
def test_an_arm_reply_of_the_wrong_type_is_fatal(tmp_path, change):
    arm = write_arm(tmp_path, {**RESULT, **change})
    with pytest.raises(HarnessError, match=next(iter(change))):
        runner.ask(arm, "stub", QUESTION, tmp_path / "run.log")


def test_an_arm_reply_that_is_not_an_object_is_fatal(tmp_path):
    with pytest.raises(HarnessError):
        runner.ask(write_arm(tmp_path, [1, 2]), "stub", QUESTION, tmp_path / "run.log")


# ---- children that hang or cannot start

def test_an_arm_that_outlives_its_limit_is_fatal(tmp_path):
    arm = tmp_path / "arm.py"
    arm.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n")
    arm.chmod(arm.stat().st_mode | stat.S_IEXEC)
    with pytest.raises(HarnessError, match="limit"):
        runner.ask(arm, "stub", QUESTION, tmp_path / "run.log", timeout_minutes=0.005)


def test_a_runner_that_is_not_installed_is_one_line_and_not_a_traceback(tmp_path):
    with pytest.raises(HarnessError, match="cannot start"):
        runner.run(str(tmp_path / "no-such-agent"), "fix it", "weak", 1, tmp_path, tmp_path / "run.log")


# ---- the judge and the synth

def test_an_envelope_with_no_result_text_is_a_hard_stop():
    with pytest.raises(HarnessError):
        util.extract_json('{"result": null, "is_error": true}')


def test_a_grade_that_is_not_a_number_is_a_hard_stop():
    with pytest.raises(HarnessError, match="NaN"):
        util.extract_json(json.dumps({"result": '{"recall": NaN, "precision": 1}'}))


def test_a_judge_that_narrates_once_is_asked_again(monkeypatch):
    replies = iter(['{"result": "I will now grade the diff."}', '{"result": "{\\"recall\\": 1}"}'])
    monkeypatch.setattr(util.subprocess, "run", lambda argv, **kwargs:
                        subprocess.CompletedProcess(argv, 0, next(replies), ""))
    assert util.claude_json("grade", "opus") == {"recall": 1}


def test_a_judge_that_hangs_is_a_hard_stop(monkeypatch):
    def hang(argv, **kwargs):
        assert kwargs["timeout"]
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
    monkeypatch.setattr(util.subprocess, "run", hang)
    with pytest.raises(HarnessError, match="limit"):
        util.claude_json("grade", "opus")


def test_a_changelog_that_comes_back_as_a_list_is_still_written(tmp_path, monkeypatch):
    (tmp_path / "baseline" / "weak" / "primes").mkdir(parents=True)
    (tmp_path / "baseline" / "weak" / "primes" / "grade.json").write_text('{"recall": 0}')
    (tmp_path / "subject.md").write_text("old")
    cfg = type("Cfg", (), {"kind": "repo", "synth_prompt": "rewrite", "synth_model": "strong",
                           "subject": tmp_path / "subject.md"})
    monkeypatch.setattr(optimize, "claude_json", lambda *args: {"subject": "new", "changelog": ["a", "b"]})
    assert optimize._synth(cfg, tmp_path, "weak", leg=None) == "new"
    assert "a" in (tmp_path / "changelog.md").read_text()


# ---- the diff and the run folder

def test_a_diff_holding_bytes_that_are_not_utf8_is_still_captured(repo, tmp_path):
    baseline, _ = capture.ground_truth(repo, "buggy", "fixed")
    work = capture.workspace(repo, "buggy", baseline, tmp_path / "work")
    (work / "latin.txt").write_bytes("caf\xe9\n".encode("latin-1"))
    assert "latin.txt" in capture.capture(work, baseline)


def test_a_run_folder_that_already_holds_a_run_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs" / "nightly").mkdir(parents=True)
    (tmp_path / "runs" / "nightly" / "scoreboard.json").write_text("{}")
    with pytest.raises(HarnessError, match="already holds"):
        cli.run_dir("nightly")


def test_two_runs_with_no_run_id_get_a_folder_each(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = cli.run_dir(None)
    first.mkdir(parents=True)
    (first / "scoreboard.json").write_text("{}")
    assert cli.run_dir(None) != first


# ---- what an installed copy ships

REPO_TASK = "\n  - {name: primes, path: ., invoke: fix, default_branch: buggy, answer_branch: fixed}"


def test_a_repo_corpus_can_name_the_prompts_proofbench_ships(tmp_path):
    (tmp_path / "subject.md").write_text("subject")
    (tmp_path / "config.yaml").write_text(
        f"models: [weak]\njudge: default\nsynth: default\nsubject: subject.md\ncorpus:{REPO_TASK}\n")
    cfg = config.load(tmp_path / "config.yaml")
    assert "ANSWER_DIFF" in cfg.judge_prompt
    assert "CURRENT_SUBJECT" in cfg.synth_prompt


def test_a_repo_task_carries_the_paths_it_ignores(tmp_path):
    (tmp_path / "config.yaml").write_text(
        f"models: [weak]\njudge: default\ncorpus:{REPO_ENTRY}, ignore: ['dist/**', notes.md]}}\n")
    assert config.load(tmp_path / "config.yaml").corpus[0].ignore == ["dist/**", "notes.md"]


def test_a_question_corpus_is_shipped_no_prompt_and_has_to_bring_its_own(tmp_path):
    with pytest.raises(HarnessError, match="its own"):
        load(tmp_path, judge="default")


def test_the_cli_reports_the_version_written_in_the_package(capsys, monkeypatch):
    """The build reads its version from this same string, so the two cannot disagree. The
    installed metadata is not compared here: an editable install keeps the version it was
    installed at, and a bump would fail this test on every machine but a fresh one."""
    import proofbench
    monkeypatch.setattr("sys.argv", ["proofbench", "--version"])
    with pytest.raises(SystemExit) as stopped:
        cli.main()
    assert stopped.value.code == 0
    assert capsys.readouterr().out.strip() == f"proofbench {proofbench.__version__}"
