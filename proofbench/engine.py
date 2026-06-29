"""The bench: corpus -> reset -> run -> capture -> judge -> scoreboard.

Models run sequentially (each reuses the same repos); tasks within a model run in
parallel (each task is a distinct repo, so no working-tree contention)."""
import json
from concurrent.futures import ThreadPoolExecutor

from . import capture, judge, runner
from .util import die, log


def _ground_truth(cfg, run_dir):
    gt = {}
    for task in cfg.corpus:
        d = run_dir / "_ground-truth" / task.name
        d.mkdir(parents=True, exist_ok=True)
        answer = capture.ground_truth(task.path, task.default_branch, task.answer_branch)
        readme = next((p for p in task.path.glob("README*")), None)
        (d / "answer.diff").write_text(answer)
        gt[task.name] = (readme.read_text() if readme else "", answer)
    return gt


def _run_and_grade(cfg, task, model, gt, out_dir):
    readme, answer = gt[task.name]
    capture.reset(task.path, task.default_branch)
    runner.run(cfg.runner, task.invoke, model, cfg.max_turns, task.path, out_dir / "run.log")
    agent_diff = capture.capture(task.path)
    (out_dir / "agent.diff").write_text(agent_diff)
    grade = judge.grade(cfg.judge_prompt, readme, answer, agent_diff, cfg.judge_model)
    grade["task"] = task.name
    (out_dir / "grade.json").write_text(json.dumps(grade, indent=2))
    return grade


def aggregate(grades):
    shared = set.intersection(*(set(judge.numeric_fields(g)) for g in grades))
    macro = {f"macro_{f}": sum(g[f] for g in grades) / len(grades) for f in shared}
    return {**macro, "tasks": {g["task"]: judge.numeric_fields(g) for g in grades}}


def bench(cfg, run_dir, models):
    gt = _ground_truth(cfg, run_dir)
    board = {}
    for model in models:
        log(f"leg [{model}] — {len(cfg.corpus)} tasks, concurrency {cfg.concurrency}")
        with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
            def work(task, model=model):
                out = run_dir / model / task.name
                out.mkdir(parents=True, exist_ok=True)
                return _run_and_grade(cfg, task, model, gt, out)
            grades = list(pool.map(work, cfg.corpus))
        board[model] = aggregate(grades)
        (run_dir / model).mkdir(parents=True, exist_ok=True)
        (run_dir / model / "scoreboard.json").write_text(json.dumps(board[model], indent=2))
    (run_dir / "scoreboard.json").write_text(json.dumps(board, indent=2))
    return board


def objective_of(board_leg, objective):
    if objective not in board_leg:
        die(f"objective '{objective}' not in scoreboard (have {list(board_leg)})")
    return board_leg[objective]
