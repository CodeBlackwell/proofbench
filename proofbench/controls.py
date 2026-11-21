"""Controls: results whose right score is known before a grader sees them.

A grader is trusted only after it has scored these as predicted. The mechanical ones are built
here from the known answer: the answer itself, nothing, half of it, and unrelated noise. Each
is written with its predicted score before anything is graded, so a prediction can never be
fitted to what the grader said. A control the builder cannot derive (a fix that breaks
something else, say) is added by hand beside these, with its own line in predictions.json."""
import json
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import capture, engine, grader, judge, question
from .util import die, spawn

NOISE = ("diff --git a/proofbench-noise.txt b/proofbench-noise.txt\nnew file mode 100644\n"
         "--- /dev/null\n+++ b/proofbench-noise.txt\n@@ -0,0 +1 @@\n"
         "+This line has nothing to do with the task.\n")
YES, NO, PARTLY = [1, 1], [0, 0], [0.01, 0.99]


def folder(cfg):
    return cfg.root / "controls"


def _canned(ids=(), text="", abstained=False):
    return {"answer_ids": list(ids), "answer": text, "abstained": abstained,
            "tokens_in": 0, "tokens_out": 0}


def _say(question_record):
    return ", ".join(question_record.get("answer_names") or question_record["answer"])


def _for_question(asked, other):
    """Canned replies to one question, each with the verdict it must get. `named` gives the
    right answer in words and no ids, so it is the one the judge has to read to pass."""
    made = {"nothing": (_canned(abstained=True), int(not asked["answerable"]))}
    if other:
        made["noise"] = (_canned(other["answer"], _say(other)), 0)
    if asked["answerable"]:
        made["answer"] = (_canned(asked["answer"]), 1)
        made["named"] = (_canned(text=_say(asked)), 1)
    half = asked["answer"][:len(asked["answer"]) // 2]
    if half:
        made["half"] = (_canned(half, ", ".join(half)), 0)
    return {name: (json.dumps(reply, indent=2), {"correct": [verdict, verdict]})
            for name, (reply, verdict) in made.items()}


def _half(diff):
    """The first half of the answer's hunks, each still under its own file header."""
    pieces = [re.split(r"(?m)^(?=@@ )", section)
              for section in re.split(r"(?m)^(?=diff --git )", diff) if section]
    keep, kept = sum(len(piece) - 1 for piece in pieces) // 2, []
    for header, *hunks in pieces:
        taken, keep = hunks[:keep], keep - len(hunks[:keep])
        kept += [header + "".join(taken)] if taken else []
    return "".join(kept)


def _for_task(task, answer):
    """A task graded by command needs no files: its starting state must fail and its answer
    must pass. A judged task without `items` gets half the answer too; with `items`, half the
    hunks may hold every listed item, so no score can be predicted for it."""
    if task.check:
        return {"start": (None, {"passed": NO}), "answer": (None, {"passed": YES})}
    made = {"answer": (answer, {"recall": YES}), "nothing": ("", {"recall": NO}),
            "noise": (NOISE, {"recall": NO})}
    if not task.items and _half(answer):
        made["half"] = (_half(answer), {"recall": PARTLY})
    return made


def _mechanical(cfg):
    """Every mechanical control of the corpus: {(owner, name): (file text, prediction)}."""
    if cfg.kind == "question":
        asked = question.read(cfg)
        wrong = {one["id"]: next((other for other in asked if other["answerable"]
                                  and other["answer"] != one["answer"]), None) for one in asked}
        return {(one["id"], name): made for one in asked
                for name, made in _for_question(one, wrong[one["id"]]).items()}
    answers = {task.name: capture.ground_truth(task.path, task.default_branch,
                                               task.answer_branch, task.ignore)[1]
               for task in cfg.corpus}
    return {(task.name, name): made for task in cfg.corpus
            for name, made in _for_task(task, answers[task.name]).items()}


def build(cfg):
    """Write the mechanical controls and their predictions. A control added by hand keeps its
    file and its prediction: only the names built here are written over."""
    suffix = ".json" if cfg.kind == "question" else ".patch"
    predictions_file = folder(cfg) / "predictions.json"
    predictions = json.loads(predictions_file.read_text()) if predictions_file.is_file() else {}
    made = _mechanical(cfg)
    for (owner, name), (text, predicted) in made.items():
        predictions[f"{owner}/{name}"] = predicted
        if text is not None:
            (folder(cfg) / owner).mkdir(parents=True, exist_ok=True)
            (folder(cfg) / owner / f"{name}{suffix}").write_text(text)
    folder(cfg).mkdir(parents=True, exist_ok=True)
    predictions_file.write_text(json.dumps(predictions, indent=2, sort_keys=True) + "\n")
    return len(made)


def _grade_questions(cfg):
    asked = {one["id"]: one for one in question.read(cfg)}

    def grade_one(path):
        owner = asked.get(path.parent.name) or die(f"control for no question of this corpus: {path}")
        return (f"{path.parent.name}/{path.stem}",
                question.grade_one(cfg, owner, json.loads(path.read_text()), cfg.judge_model))
    with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
        return dict(pool.map(grade_one, sorted(folder(cfg).glob("*/*.json"))))


def _check_both_ends(cfg, task, answer, work):
    yield f"{task.name}/start", grader.run_check(task, work, cfg.timeout_minutes)
    applied = spawn(["git", "-C", str(work), "apply", "-"], input=answer)
    if applied.returncode != 0:
        die(f"{task.name}: the answer does not apply to the starting state: {applied.stderr.strip()}")
    yield f"{task.name}/answer", grader.run_check(task, work, cfg.timeout_minutes)


def _grade_task(cfg, task):
    baseline, answer = capture.ground_truth(task.path, task.default_branch, task.answer_branch,
                                            task.ignore)
    with tempfile.TemporaryDirectory(prefix="proofbench-", ignore_cleanup_errors=True) as scratch:
        work = capture.workspace(task.path, task.default_branch, baseline, Path(scratch) / task.name)
        if task.check:
            yield from _check_both_ends(cfg, task, answer, work)
            return
        readme = engine.read_readme(work)
    for path in sorted((folder(cfg) / task.name).glob("*.patch")):
        grade, cost_usd = judge.grade(cfg.judge_prompt, readme, answer, path.read_text(),
                                      cfg.judge_model, task.items,
                                      limit_kb=cfg.judge_input_limit_kb, name=str(path))
        yield f"{task.name}/{path.stem}", {**grade, "judge_cost_usd": cost_usd}


def grade(cfg):
    """Every control of the corpus, graded exactly as an agent's result would be."""
    if cfg.kind == "question":
        return _grade_questions(cfg)
    return {key: graded for task in cfg.corpus for key, graded in _grade_task(cfg, task)}
