"""The command grader, and the limit on what a judge is sent."""
import pytest

from proofbench import config, engine, grader, judge, runner
from proofbench.util import HarnessError

from .conftest import git

CHECK = "python3 -c 'import a, sys; sys.exit(a.x != 2)'"


def checked_task(repo, **named):
    return config.Task(name="fix", path=repo, invoke="go", default_branch="buggy",
                       answer_branch="fixed", check=CHECK, **named)


def write_config(repo, entry, judge_line=""):
    path = repo.parent / "proofbench.yaml"
    path.write_text(f"models: [weak]\n{judge_line}corpus:\n  - {entry}\n")
    return path


def entry(repo, more=""):
    return (f"{{name: fix, path: {repo}, invoke: go, default_branch: buggy, "
            f"answer_branch: fixed{more}}}")


def test_a_check_passes_on_the_fix_and_fails_on_the_starting_state(repo, tmp_path):
    """Two clones, because the first check leaves a bytecode cache the second would read."""
    for branch, passed in (("buggy", 0), ("fixed", 1)):
        git(repo, "clone", "-q", "--branch", branch, str(repo), str(tmp_path / branch))
        assert grader.run_check(checked_task(repo), tmp_path / branch)["passed"] == passed


def test_hidden_files_come_from_the_answer_branch_over_what_the_agent_left(repo, tmp_path):
    """An agent that edits the test to pass is graded by the test it never saw."""
    git(repo, "checkout", "-q", "fixed")
    (repo / "test_a.py").write_text("import a\nassert a.x == 2\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "the held-back test")
    git(repo, "checkout", "-q", "buggy")
    work = tmp_path / "clone"
    git(repo, "clone", "-q", str(repo), str(work))
    (work / "test_a.py").write_text("pass\n")
    task = config.Task(name="fix", path=repo, invoke="go", default_branch="buggy",
                       answer_branch="fixed", check="python3 test_a.py", hidden=["test_a.py"])
    assert grader.run_check(task, work)["passed"] == 0


def test_a_task_graded_by_command_is_never_sent_to_the_judge(repo, tmp_path, monkeypatch):
    def fix_it(runner_name, invoke, model, max_turns, cwd, log_path, timeout_minutes=None):
        (cwd / "a.py").write_text("x = 2\n")
        return {"seconds": 1, "cost_usd": None, "turns": None}
    monkeypatch.setattr(runner, "run", fix_it)
    monkeypatch.setattr(judge, "grade", lambda *args, **named: pytest.fail("the judge was asked"))
    cfg = config.load(write_config(repo, entry(repo, f', check: "{CHECK}"')))
    leg = engine.bench(cfg, tmp_path / "run", cfg.models)["weak"]
    assert (cfg.objective, leg["macro_passed"], cfg.judge_prompt) == ("macro_passed", 1.0, None)


@pytest.mark.parametrize("entries, refusal", [
    ("{more}, hidden: [test_a.py]}}", "has none"),
    ("{more}, check: \"true\"}}\n  - {more}, name: other}}", "mixes tasks"),
])
def test_a_corpus_the_command_grader_cannot_serve_is_refused(repo, entries, refusal):
    path = write_config(repo, entries.format(more=entry(repo)[:-1]), "judge: default\n")
    with pytest.raises(HarnessError, match=refusal):
        config.load(path)


def test_a_judged_corpus_still_needs_a_rubric(repo):
    with pytest.raises(HarnessError, match="no judge prompt"):
        config.load(write_config(repo, entry(repo)))


def test_a_judge_input_over_the_limit_stops_the_run_and_names_the_task(monkeypatch):
    """Cut to fit, the diff would be graded on part of the evidence, so nothing is sent."""
    monkeypatch.setattr(judge, "claude_json", lambda *args: pytest.fail("the judge was asked"))
    with pytest.raises(HarnessError, match="judge input for big-task is 3 KB"):
        judge.grade("rubric", "readme", "answer", "x" * 3000, "opus", limit_kb=2, name="big-task")
    question = {"id": "Q9", "text": "?", "answer": ["a"]}
    with pytest.raises(HarnessError, match="judge input for Q9"):
        judge.grade_answer("rubric", question, {"answer": "y" * 3000, "answer_ids": []}, "opus", 2)


def test_the_limit_is_read_from_the_config_and_has_to_be_a_size(repo):
    path = write_config(repo, entry(repo), "judge: default\njudge_input_limit_kb: 50\n")
    assert config.load(path).judge_input_limit_kb == 50
    path.write_text(path.read_text().replace("50", "none"))
    with pytest.raises(HarnessError, match="judge_input_limit_kb"):
        config.load(path)
