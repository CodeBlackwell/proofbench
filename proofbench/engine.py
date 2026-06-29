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
    meta = runner.run(cfg.runner, task.invoke, model, cfg.max_turns, task.path, out_dir / "run.log")
    cost = f", ${meta['cost_usd']:.3f}" if meta["cost_usd"] is not None else ""
    log(f"[{model}] {task.name}: {meta['seconds']}s{cost}"
        + (f", {meta['turns']} turns" if meta["turns"] else ""))
    agent_diff = capture.capture(task.path, task.default_branch)
    (out_dir / "agent.diff").write_text(agent_diff)
    if not agent_diff.strip():
        log(f"\033[33m[{model}] {task.name}: EMPTY diff — agent changed nothing; "
            f"excluded from macro (check the invoke if this is unexpected)\033[0m")
        grade = {"task": task.name, "empty_capture": True}
    else:
        grade = judge.grade(cfg.judge_prompt, readme, answer, agent_diff, cfg.judge_model)
        grade["task"] = task.name
    grade["_meta"] = meta
    (out_dir / "grade.json").write_text(json.dumps(grade, indent=2))
    return grade


def _resources(grades):
    """Sum cost + wall-clock across the whole leg, empty captures included: a run that
    changed nothing still spent money and time. cost_usd is None when no leg task reported
    it (a non-claude runner)."""
    metas = [g.get("_meta", {}) for g in grades]
    costs = [m["cost_usd"] for m in metas if m.get("cost_usd") is not None]
    return {"seconds": round(sum(m.get("seconds") or 0 for m in metas), 1),
            "cost_usd": round(sum(costs), 4) if costs else None,
            "turns": sum(m.get("turns") or 0 for m in metas) or None}


def aggregate(grades):
    """Macro-average the shared numeric fields. Empty-capture tasks carry no metrics: they
    are excluded from the average and listed separately so they never become a silent zero."""
    graded = [g for g in grades if not g.get("empty_capture")]
    out = {"tasks": {g["task"]: judge.numeric_fields(g) for g in grades}}
    empty = [g["task"] for g in grades if g.get("empty_capture")]
    if empty:
        out["empty_captures"] = empty
    if graded:
        shared = set.intersection(*(set(judge.numeric_fields(g)) for g in graded))
        out.update({f"macro_{f}": sum(g[f] for g in graded) / len(graded) for f in shared})
    out["resources"] = _resources(grades)
    return out


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
