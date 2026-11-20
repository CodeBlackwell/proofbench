"""The corpus half of a config: what the tasks are, and the entries that are refused."""
from dataclasses import dataclass, field
from pathlib import Path

from .util import die

TASK_KEYS = ("name", "path", "invoke", "default_branch", "answer_branch")
# The keys an entry may carry beside the ones it must. A misspelt `holdout` or `ignore` would
# otherwise be dropped in silence and the run would grade something other than what was asked.
OPTIONAL = {"repo": {"kind", "holdout", "ignore"}, "question": {"kind", "holdout"}}


@dataclass
class Task:
    name: str
    path: Path           # the repo the agent works in
    invoke: str          # what the agent is asked to do, e.g. "/crg-debug"
    default_branch: str  # the broken / initial state
    answer_branch: str   # the ground-truth fixed state
    holdout: bool = False  # scored by the optimize gate, never shown to the synth
    ignore: list = field(default_factory=list)  # path patterns left out of both diffs


@dataclass
class QuestionSet:
    name: str
    path: Path           # JSONL, one question per line, with its known answer
    holdout: bool = False  # scored by the optimize gate, never shown to the synth


def _held(entry):
    held = entry.get("holdout", False)
    return held if isinstance(held, bool) else die(f"holdout must be true or false: {entry}")


def _ignored(entry):
    """Paths the answer branch touches that are not the fix: a rebuilt bundle, a README, a file
    of notes. Left in, each is an item no agent should reproduce, and recall is graded on it."""
    paths = entry.get("ignore", [])
    if not isinstance(paths, list) or any(not isinstance(one, str) for one in paths):
        die(f"ignore must be a list of path patterns: {entry}")
    return paths


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


def _need(entries, keys, optional):
    for entry in entries:
        missing = [key for key in keys if key not in entry]
        unknown = sorted(set(entry) - set(keys) - optional)
        if missing:
            die(f"corpus entry {entry} is missing {missing}")
        if unknown:
            die(f"corpus entry {entry} carries keys proofbench does not read: {unknown}")


def read_corpus(entries, resolve):
    """One corpus, one kind: a mixed corpus would need two capture paths inside one leg."""
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        die(f"corpus must be a list of entries: {entries!r}")
    kinds = {entry.get("kind", "repo") for entry in entries}
    if len(kinds) > 1:
        die(f"corpus mixes task kinds: {sorted(kinds)}")
    kind = kinds.pop()
    if kind not in OPTIONAL:
        die(f"unknown corpus kind: {kind}")
    _need(entries, ("file",) if kind == "question" else TASK_KEYS, OPTIONAL[kind])
    if kind == "question":
        return kind, [QuestionSet(name=Path(entry["file"]).stem, holdout=_held(entry),
                                  path=_question_file(resolve(entry["file"]))) for entry in entries]
    return kind, _refuse_shared_names([
        Task(name=entry["name"], path=resolve(entry["path"]), invoke=entry["invoke"],
             default_branch=entry["default_branch"], answer_branch=entry["answer_branch"],
             holdout=_held(entry), ignore=_ignored(entry))
        for entry in entries])
