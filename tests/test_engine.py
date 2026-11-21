"""End-to-end engine wiring (ground truth -> clone -> run -> capture -> judge -> scoreboard),
exercised with a stub runner and stub judge so it needs no `claude`. The first test requires
the demo corpus (run `bash examples/sample-corpus/build.sh` first); the rest build their own
repo."""
import json
from pathlib import Path

import pytest

from proofbench import config, engine, judge, runner
from proofbench.util import HarnessError

from .conftest import git

DEMO = Path(__file__).resolve().parent.parent / "examples" / "proofbench.demo.yaml"
FIXED = "def is_prime(n):\n    return n > 1 and all(n % i for i in range(2, int(n ** 0.5) + 1))\n"


@pytest.mark.skipif(not (DEMO.parent / "sample-corpus/repos/primes").exists(),
                    reason="run examples/sample-corpus/build.sh first")
def test_bench_wires_end_to_end(tmp_path, monkeypatch):
    cfg = config.load(DEMO)

    # stub runner: a "perfect agent" that applies a correct fix to lib.py in the repo
    def fake_run(runner_name, invoke, model, max_turns, cwd, log_path, timeout_minutes=None):
        (Path(cwd) / "lib.py").write_text(FIXED)
        Path(log_path).write_text("stub")
        return {"seconds": 1.0, "cost_usd": 0.01, "turns": 2}
    monkeypatch.setattr(runner, "run", fake_run)

    # stub judge: credit recall when the agent actually changed something
    def fake_grade(prompt, readme, answer, agent_diff, model, items=(), **named):
        return {"recall": 1.0 if agent_diff.strip() else 0.0, "precision": 1.0}, 0.05
    monkeypatch.setattr(judge, "grade", fake_grade)

    board = engine.bench(cfg, tmp_path, cfg.models)
    leg = board[cfg.models[0]]
    assert leg["macro_recall"] == 1.0
    assert leg["macro_precision"] == 1.0
    assert leg["resources"] == {"seconds": 2.0, "cost_usd": 0.02, "turns": 4,
                                "judge_cost_usd": 0.1}
    saved = json.loads((tmp_path / "scoreboard.json").read_text())
    assert set(saved[cfg.models[0]]["tasks"]) == {"primes", "ranges"}
    grade = json.loads((tmp_path / cfg.models[0] / "primes" / "grade.json").read_text())
    assert grade["_meta"]["judge_cost_usd"] == 0.05


def _repo_config(repo, invokes):
    tasks = [config.Task(name=name, path=repo, invoke=invoke, default_branch="buggy",
                         answer_branch="fixed") for name, invoke in invokes.items()]
    return config.Config(root=repo, runner="claude", models=["weak"], judge_model="strong",
                         synth_model="strong", objective="macro_recall", concurrency=2,
                         max_turns=1, judge_prompt="grade it", corpus=tasks)


@pytest.fixture
def bench_two_tasks(repo, tmp_path, monkeypatch):
    """One agent fixes its task and the other changes nothing. The judge is a stub that gives
    recall 1 exactly when the diff holds the fix, so an empty diff is graded 0, never skipped."""
    seen = {"cwds": [], "readmes": []}

    def fake_run(runner_name, invoke, model, max_turns, cwd, log_path, timeout_minutes=None):
        seen["cwds"].append(Path(cwd))
        if invoke == "fix it":
            (Path(cwd) / "a.py").write_text("x = 2\n")
        return {"seconds": 1.0, "cost_usd": None, "turns": None}

    def fake_grade(prompt, readme, answer, agent_diff, model, items=(), **named):
        seen["readmes"].append(readme)
        return {"recall": 1.0 if "+x = 2" in agent_diff else 0.0}, None
    monkeypatch.setattr(runner, "run", fake_run)
    monkeypatch.setattr(judge, "grade", fake_grade)
    cfg = _repo_config(repo, {"fixes": "fix it", "idles": "do nothing"})
    return engine.bench(cfg, tmp_path / "run", cfg.models)["weak"], seen, repo, tmp_path / "run"


def test_an_agent_that_changes_nothing_is_a_zero_in_the_macro(bench_two_tasks):
    leg, *_ = bench_two_tasks
    assert leg["macro_recall"] == 0.5
    assert leg["empty_captures"] == ["idles"]


def test_the_agent_runs_outside_the_corpus_repo_and_the_run_directory(bench_two_tasks):
    _, seen, repo, run_dir = bench_two_tasks
    for cwd in seen["cwds"]:
        assert cwd != repo
        assert run_dir not in cwd.parents
    assert (repo / "a.py").read_text() == "x = 1\n"


def test_the_judge_reads_the_readme_the_baseline_commit_holds(repo, tmp_path, monkeypatch):
    (repo / "README.md").write_text("left behind by an earlier run\n")
    readmes = []
    monkeypatch.setattr(runner, "run", lambda *args: {"seconds": 0, "cost_usd": None, "turns": None})
    monkeypatch.setattr(judge, "grade", lambda prompt, readme, *rest, **named: readmes.append(readme) or ({"recall": 0}, None))
    cfg = _repo_config(repo, {"only": "do nothing"})
    engine.bench(cfg, tmp_path / "run", cfg.models)
    assert readmes == ["Fix x.\n"]


def test_aggregate_counts_an_empty_capture_in_the_average():
    grades = [{"task": "a", "recall": 1.0}, {"task": "b", "recall": 0.0, "empty_capture": True}]
    board = engine.aggregate(grades)
    assert board["macro_recall"] == 0.5
    assert board["empty_captures"] == ["b"]


def test_two_tasks_sharing_a_name_are_refused(tmp_path):
    (tmp_path / "judge.md").write_text("grade it")
    entry = "  - {name: primes, path: ., invoke: fix, default_branch: buggy, answer_branch: fixed}\n"
    (tmp_path / "config.yaml").write_text("models: [weak]\njudge: judge.md\ncorpus:\n" + entry * 2)
    with pytest.raises(HarnessError, match="not unique"):
        config.load(tmp_path / "config.yaml")


def test_a_task_s_ignored_paths_reach_neither_side_of_the_grade(repo, tmp_path, monkeypatch):
    git(repo, "checkout", "-q", "fixed")
    (repo / "notes.md").write_text("the answers\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "notes")
    git(repo, "checkout", "-q", "buggy")
    graded = {}

    def fake_run(runner_name, invoke, model, max_turns, cwd, log_path, timeout_minutes=None):
        (Path(cwd) / "notes.md").write_text("the agent wrote notes too\n")
        (Path(cwd) / "a.py").write_text("x = 2\n")
        return {"seconds": 0, "cost_usd": None, "turns": None}
    monkeypatch.setattr(runner, "run", fake_run)
    monkeypatch.setattr(judge, "grade", lambda prompt, readme, answer, agent_diff, model, items=(), **named:
                        graded.update(answer=answer, agent=agent_diff) or ({"recall": 1.0}, None))
    cfg = _repo_config(repo, {"only": "fix it"})
    cfg.corpus[0].ignore = ["notes.md"]
    engine.bench(cfg, tmp_path / "run", cfg.models)
    assert "+x = 2" in graded["answer"] and "+x = 2" in graded["agent"]
    assert "notes.md" not in graded["answer"] and "notes.md" not in graded["agent"]


def test_a_readme_named_in_lower_case_still_reaches_the_judge(repo, tmp_path, monkeypatch):
    git(repo, "mv", "README.md", "readme.md")
    git(repo, "commit", "-qm", "lower case readme")
    readmes = []
    monkeypatch.setattr(runner, "run", lambda *args: {"seconds": 0, "cost_usd": None, "turns": None})
    monkeypatch.setattr(judge, "grade", lambda prompt, readme, *rest, **named: readmes.append(readme) or ({"recall": 0}, None))
    cfg = _repo_config(repo, {"only": "do nothing"})
    engine.bench(cfg, tmp_path / "run", cfg.models)
    assert readmes == ["Fix x.\n"]


def test_a_task_s_items_reach_the_judge(repo, tmp_path, monkeypatch):
    handed = []
    monkeypatch.setattr(runner, "run", lambda *args: {"seconds": 0, "cost_usd": None, "turns": None})
    monkeypatch.setattr(judge, "grade", lambda *args, **named: handed.append(args[5]) or ({"recall": 0}, None))
    cfg = _repo_config(repo, {"only": "do nothing"})
    cfg.corpus[0].items = ["x is 2"]
    engine.bench(cfg, tmp_path / "run", cfg.models)
    assert handed == [["x is 2"]]
