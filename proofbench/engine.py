"""The bench: corpus -> clone -> run -> capture -> judge -> scoreboard.

Models run sequentially; tasks within a model run in parallel. Every attempt gets its own
throwaway clone, so no two attempts share a working tree and the corpus repos are only read."""
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import capture, judge, question, runner
from .util import die, log


def _ground_truth(cfg, run_dir):
    """Each task's baseline commit and answer diff, pinned before any agent runs."""
    gt = {}
    for task in cfg.corpus:
        d = run_dir / "_ground-truth" / task.name
        d.mkdir(parents=True, exist_ok=True)
        gt[task.name] = capture.ground_truth(task.path, task.default_branch, task.answer_branch)
        (d / "answer.diff").write_text(gt[task.name][1])
    return gt


def _attempt(cfg, task, model, baseline, out_dir):
    """One agent run in a clone under the system temp directory: outside the corpus repo, which
    holds the answer branch, and outside the run directory, which holds the answer diff. The
    README is the one the baseline commit holds, read before the agent can touch it."""
    with tempfile.TemporaryDirectory(prefix="proofbench-", ignore_cleanup_errors=True) as scratch:
        work = capture.workspace(task.path, task.default_branch, baseline, Path(scratch) / task.name)
        readme = next((p.read_text() for p in sorted(work.glob("README*")) if p.is_file()), "")
        meta = runner.run(cfg.runner, task.invoke, model, cfg.max_turns, work,
                          out_dir / "run.log", cfg.timeout_minutes)
        return readme, meta, capture.capture(work, baseline)


def _run_and_grade(cfg, task, model, gt, out_dir):
    baseline, answer = gt[task.name]
    readme, meta, agent_diff = _attempt(cfg, task, model, baseline, out_dir)
    cost = f", ${meta['cost_usd']:.3f}" if meta["cost_usd"] is not None else ""
    log(f"[{model}] {task.name}: {meta['seconds']}s{cost}"
        + (f", {meta['turns']} turns" if meta["turns"] else ""))
    (out_dir / "agent.diff").write_text(agent_diff)
    grade = judge.grade(cfg.judge_prompt, readme, answer, agent_diff, cfg.judge_model)
    grade.update(task=task.name, _meta=meta)
    if not agent_diff.strip():
        grade["empty_capture"] = True
        log(f"\033[33m[{model}] {task.name}: EMPTY diff: the agent changed nothing, and the "
            f"judge graded that as it stands (check the invoke if this is unexpected)\033[0m")
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
    """Macro-average the shared numeric fields over every task. A task the agent left untouched
    is graded like any other and named under empty_captures: leaving it out of the average would
    let an agent raise its score by giving up on the tasks it cannot do."""
    out = {"tasks": {g["task"]: judge.numeric_fields(g) for g in grades}}
    empty = [g["task"] for g in grades if g.get("empty_capture")]
    if empty:
        out["empty_captures"] = empty
    shared = set.intersection(*(set(judge.numeric_fields(g)) for g in grades))
    out.update({f"macro_{f}": sum(g[f] for g in grades) / len(grades) for f in shared})
    out["resources"] = _resources(grades)
    return out


def bench(cfg, run_dir, models):
    if cfg.kind == "question":
        return question.bench(cfg, run_dir, models)
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
    if board_leg[objective] is None:
        die(f"objective '{objective}' is undefined on this leg, so nothing can be compared")
    return board_leg[objective]
