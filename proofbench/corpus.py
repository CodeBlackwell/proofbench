"""The corpus half of a config: what the tasks are, and the entries that are refused."""
from dataclasses import dataclass
from pathlib import Path

from .util import die

TASK_KEYS = ("name", "path", "invoke", "default_branch", "answer_branch")


@dataclass
class Task:
    name: str
    path: Path           # the repo the agent works in
    invoke: str          # what the agent is asked to do, e.g. "/crg-debug"
    default_branch: str  # the broken / initial state
    answer_branch: str   # the ground-truth fixed state
    holdout: bool = False  # scored by the optimize gate, never shown to the synth


@dataclass
class QuestionSet:
    name: str
    path: Path           # JSONL, one question per line, with its known answer
    holdout: bool = False  # scored by the optimize gate, never shown to the synth


def _held(entry):
    held = entry.get("holdout", False)
    return held if isinstance(held, bool) else die(f"holdout must be true or false: {entry}")


def _question_file(path):
    return path if path.is_file() else die(f"question file not found: {path}")


def _refuse_shared_names(tasks):
    """The answer key and the output directory are both keyed by task name, so two tasks sharing
    one would be graded against a single answer and written over each other."""
    names = [task.name for task in tasks]
    shared = sorted({name for name in names if names.count(name) > 1})
    if shared:
        die(f"task names are not unique: {shared}")
    return tasks


def _need(entries, keys):
    for entry in entries:
        missing = [key for key in keys if key not in entry]
        if missing:
            die(f"corpus entry {entry} is missing {missing}")


def read_corpus(entries, resolve):
    """One corpus, one kind: a mixed corpus would need two capture paths inside one leg."""
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        die(f"corpus must be a list of entries: {entries!r}")
    kinds = {entry.get("kind", "repo") for entry in entries}
    if len(kinds) > 1:
        die(f"corpus mixes task kinds: {sorted(kinds)}")
    kind = kinds.pop()
    _need(entries, ("file",) if kind == "question" else TASK_KEYS if kind == "repo" else ())
    if kind == "question":
        return kind, [QuestionSet(name=Path(entry["file"]).stem, holdout=_held(entry),
                                  path=_question_file(resolve(entry["file"]))) for entry in entries]
    if kind != "repo":
        die(f"unknown corpus kind: {kind}")
    return kind, _refuse_shared_names([
        Task(name=entry["name"], path=resolve(entry["path"]), invoke=entry["invoke"],
             default_branch=entry["default_branch"], answer_branch=entry["answer_branch"],
             holdout=_held(entry))
        for entry in entries])
