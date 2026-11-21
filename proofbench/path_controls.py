"""Controls for the path graders: step logs whose right grade is known before one is read.

The mechanical ones are a recorded good path as it was, and the same path ruined in the ways
this eval's own rules name: emptied, with a required tool's calls taken out, and with two
ordered tools turned round. Each keeps the recording's answer file, so a rule script meets the
files it meets on a run. What only a script or the rubric can catch has no mechanical control:
that one is written by hand, as a folder beside these with its own line in predictions.json."""
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import capture, engine, paths, question, steps
from .util import die

SUFFIX = ".path"


def _first(cfg, kind):
    return next((value for rule, value in cfg.path.rules if rule == kind), None)


def _predict(cfg, rules_held, sound):
    """A prediction for each grader this eval has. `rules_held` is None where no rule of the
    eval decides the control either way, and then nothing is predicted of the rules."""
    predicted = {}
    if cfg.path.rules and rules_held is not None:
        predicted["rules_held"] = [rules_held, rules_held]
    if cfg.path.judge_prompt:
        predicted["path_sound"] = [sound, sound]
    return predicted


def _variants(cfg, logged):
    """The controls one recorded path yields: {name: (steps, prediction)}. A way of ruining it
    is used only when a rule of the eval names what it ruins, so every prediction follows from
    something the owner declared and none from a guess about what a good path is."""
    tools = [step["tool"] for step in logged]
    required, ordered = _first(cfg, "called"), _first(cfg, "before")
    made = {"good": (logged, _predict(cfg, 1, 1)),
            "empty": ([], _predict(cfg, 0 if required else None, 0))}
    if required in tools:
        made["removed"] = ([step for step in logged if step["tool"] != required],
                           _predict(cfg, 0, 0))
    if ordered and set(ordered) <= set(tools):
        late = [step for step in logged if step["tool"] == ordered[0]]
        made["reordered"] = ([step for step in logged if step not in late] + late,
                             _predict(cfg, 0, 0))
    return {name: one for name, one in made.items() if one[1]}


def build(cfg, folder):
    """Write the mechanical controls of every recorded path. Returns their predictions."""
    predictions = {}
    for recorded in sorted((cfg.root / paths.RECORDED).glob(f"*/{steps.FILE}")):
        owner = recorded.parent
        for name, (logged, predicted) in _variants(cfg, steps.read(recorded)).items():
            made = folder / owner.name / f"{name}{SUFFIX}"
            shutil.copytree(owner, made, dirs_exist_ok=True)
            steps.write(made / steps.FILE, logged)
            predictions[f"{owner.name}/{name}{SUFFIX}"] = predicted
    return predictions


def _task_texts(cfg):
    """What each task asked, as the path judge is shown it on a run."""
    if cfg.kind == "question":
        return {one["id"]: one["text"] for one in question.read(cfg)}
    texts = {}
    with tempfile.TemporaryDirectory(prefix="proofbench-", ignore_cleanup_errors=True) as scratch:
        for task in cfg.corpus:
            baseline, _ = capture.ground_truth(task.path, task.default_branch,
                                               task.answer_branch, task.ignore)
            work = capture.workspace(task.path, task.default_branch, baseline,
                                     Path(scratch) / task.name)
            texts[task.name] = engine.describe(task, engine.read_readme(work))
    return texts


def grade(cfg, folder):
    """Every path control of the corpus, graded exactly as a run's path would be."""
    found = sorted(folder.glob(f"*/*{SUFFIX}"))
    texts = _task_texts(cfg) if found else {}

    def grade_one(control):
        owner = control.parent.name
        if owner not in texts:
            die(f"path control for no task of this corpus: {control}")
        fields, cost_usd = paths.grade(cfg, texts[owner], owner, control)
        return f"{owner}/{control.name}", {**fields, "judge_cost_usd": cost_usd}
    with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
        return dict(pool.map(grade_one, found))
