"""The gates an eval passes before its scores are worth reading.

Each is decided here, by a command, and recorded in a state file beside the config that only
these commands write. A record carries a hash of what the gate covered, so an eval whose tasks,
rubric, adapter or controls changed since reads as stale, and a stale gate is not a passed one."""
import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path

import yaml

from . import capture, controls, engine, path_controls, paths, question, runner, steps
from .util import HarnessError, die, log, sum_reported

STATE = "gates.json"
# What each gate's hash covers. The system under test is in none of them: it changes all the
# time, and an eval that went stale whenever its subject did could never be used on it. The
# `path` key is covered apart from the rest of the config: how the path is graded says nothing
# about coverage or headroom, and the adapter gate depends only on whether it is graded at all.
COVERS = {"adapter": ("config", "has_path", "runner"),
          "coverage": ("config", "tasks"),
          "controls": ("config", "path", "path_files", "tasks", "judge", "controls"),
          "headroom": ("config", "runner", "tasks", "judge")}
GATES = tuple(COVERS)


def _tasks(cfg):
    if cfg.kind == "question":
        return [task.path.read_bytes() for task in cfg.corpus]
    return [capture.pin(task.path, ref).encode() for task in cfg.corpus
            for ref in (task.default_branch, task.answer_branch)]


def _files(folder):
    found = sorted(path for path in folder.rglob("*") if path.is_file())
    return [str(path.relative_to(folder)).encode() + path.read_bytes() for path in found]


def _keys(cfg, is_covered):
    """The config as it parses, so a reworded comment turns no gate stale."""
    raw = yaml.safe_load(cfg.file.read_text()).items()
    kept = {key: value for key, value in raw if is_covered(key)}
    return [json.dumps(kept, sort_keys=True).encode()]


def _path_files(cfg):
    """What the path graders read beside the config: the rubric, each rule script, and the
    recorded paths the judge is shown and the mechanical controls are built from."""
    if not cfg.path:
        return []
    scripts = [Path(value).read_bytes() for kind, value in cfg.path.rules if kind == "script"]
    return [(cfg.path.judge_prompt or "").encode(), *scripts, *_files(cfg.root / paths.RECORDED)]


def _runner(cfg):
    return [Path(cfg.runner).read_bytes() if Path(cfg.runner).is_file() else cfg.runner.encode()]


# How often and how many at once a run asks changes no gate's verdict, so neither is covered.
APART = ("path", "trials", "concurrency")
PARTS = {"config": lambda cfg: _keys(cfg, lambda key: key not in APART),
         "path": lambda cfg: _keys(cfg, lambda key: key == "path"),
         "has_path": lambda cfg: [str(bool(cfg.path)).encode()],
         "path_files": _path_files, "runner": _runner, "tasks": _tasks,
         "judge": lambda cfg: [(cfg.judge_prompt or "").encode()],
         "controls": lambda cfg: _files(controls.folder(cfg))}


def _hash(cfg, gate):
    digest = hashlib.sha256()
    for part in COVERS[gate]:
        for chunk in PARTS[part](cfg):
            digest.update(len(chunk).to_bytes(8, "big") + chunk)
    return digest.hexdigest()


def _records(cfg):
    path = cfg.root / STATE
    return json.loads(path.read_text()) if path.is_file() else {}


def status(cfg):
    """Each gate as it stands now: passed, failed, stale, or not run."""
    states = {}
    for gate in GATES:
        record = _records(cfg).get(gate)
        if record is None:
            states[gate] = "not run"
        elif record["covers"] != _hash(cfg, gate):
            states[gate] = "stale"
        else:
            states[gate] = "passed" if record["passed"] else "failed"
    return states


def refuse_unchecked(cfg):
    """A score from an eval nobody checked reads exactly like one from an eval that works."""
    open_gates = [f"{gate} ({state})" for gate, state in status(cfg).items() if state != "passed"]
    if open_gates:
        die(f"this eval has not passed its gates: {', '.join(open_gates)}. Run "
            f"`proofbench check GATE` for each, or pass --unchecked to run it anyway")


def _logged(cfg, run_dir):
    """An eval that grades the path needs the adapter's step log as much as its result, and a
    log that is missing stops the gate here."""
    return f", and {len(steps.read(run_dir / steps.FILE))} steps" if cfg.path else ""


def _adapter(cfg, run_dir):
    """One task through the adapter on the cheapest model: it starts, and a result comes back."""
    model = cfg.models[-1]
    run_dir.mkdir(parents=True)
    if cfg.kind == "question":
        asked = question.read(cfg)[0]
        result = runner.ask(cfg.runner, model, asked, run_dir / "run.log", cfg.runner_args,
                            cfg.timeout_minutes, run_dir / steps.FILE if cfg.path else None)
        return True, result.get("cost_usd"), f"{asked['id']} gave a result" + _logged(cfg, run_dir)
    task = cfg.corpus[0]
    baseline, _ = capture.ground_truth(task.path, task.default_branch, task.answer_branch, task.ignore)
    _, meta, agent_diff, _ = engine.attempt(cfg, task, model, baseline, run_dir)
    changed = bool(agent_diff.strip())
    said = "a diff was captured" if changed else "the agent changed nothing"
    return changed, meta["cost_usd"], f"{task.name}: {said}" + _logged(cfg, run_dir)


def _coverage(cfg, run_dir):
    """Every answer class the config declares has a task. A score over an eval that never asks
    for one kind of answer cannot catch a system that always, or never, gives it."""
    if not cfg.classes:
        die("config declares no `classes`: list the kinds of answer this eval must cover")
    labels = ([one.get("class") for one in question.read(cfg)] if cfg.kind == "question"
              else [task.answer_class for task in cfg.corpus])
    empty = [name for name in cfg.classes if name not in labels]
    outside = sum(label not in cfg.classes for label in labels)
    detail = f"classes with no task: {empty}; tasks in no declared class: {outside}"
    return not empty and not outside, None, detail


def _held(graded, predicted):
    return all(field in graded and low <= graded[field] <= high
               for field, (low, high) in predicted.items())


def _controls(cfg, run_dir):
    """Every control scored inside its predicted range, and none left without a prediction.
    An eval that grades the path has path controls too: its path graders are graders."""
    predictions = json.loads((controls.folder(cfg) / "predictions.json").read_text())
    graded = controls.grade(cfg)
    run_dir.mkdir(parents=True)
    (run_dir / "controls.json").write_text(json.dumps(graded, indent=2))
    unpaired = sorted(set(predictions) ^ set(graded))
    missed = sorted(key for key in set(predictions) & set(graded)
                    if not _held(graded[key], predictions[key]))
    cost = sum_reported(one.get("judge_cost_usd") for one in graded.values())
    of_paths = sum(key.endswith(path_controls.SUFFIX) for key in graded)
    detail = (f"{len(graded)} controls, {of_paths} of them for the path; "
              f"outside their prediction: {missed}; unpaired: {unpaired}")
    is_covered = bool(graded) and (of_paths or not cfg.path)
    return bool(is_covered) and not missed and not unpaired, cost, detail


def _spent(leg):
    """What a leg cost, agents and judge together, as far as either was reported."""
    used = leg.get("resources", {})
    return sum_reported([leg.get("cost_usd"), used.get("cost_usd"), used.get("judge_cost_usd"),
                         *(record.get(name) for record in leg.get("records", [])
                           for name in ("judge_cost_usd", "path_judge_cost_usd"))])


def _headroom(cfg, run_dir):
    """The strongest model on the whole eval, each task once whatever `trials` says. An eval it
    scores everything on cannot show a change for the better, and one it scores nothing on is
    asking what nothing it is shown can answer. Neither can tell two systems apart."""
    strongest = cfg.models[0]
    leg = engine.bench(replace(cfg, trials=1), run_dir, [strongest])[strongest]
    named = cfg.objective if cfg.kind == "repo" else next(
        name for name in ("accuracy", "abstention_rate") if name in leg)
    score = engine.objective_of(leg, named)
    return 0 < score < 1, _spent(leg), f"{strongest} scored {named}={score:.3f}"


RUN = {"adapter": _adapter, "coverage": _coverage, "controls": _controls, "headroom": _headroom}


def check(cfg, gate, run_dir):
    """Run one gate and record how it went. A gate that could not finish is a gate that failed,
    and the reason is kept."""
    covers = _hash(cfg, gate)
    try:
        passed, cost_usd, detail = RUN[gate](cfg, run_dir)
    except HarnessError as failure:
        passed, cost_usd, detail = False, None, str(failure)
    record = {"passed": passed, "at": time.strftime("%Y-%m-%d"), "cost_usd": cost_usd,
              "covers": covers, "detail": detail}
    (cfg.root / STATE).write_text(json.dumps({**_records(cfg), gate: record}, indent=2) + "\n")
    log(f"gate {gate}: {'passed' if passed else 'FAILED'}: {detail}")
    return passed
