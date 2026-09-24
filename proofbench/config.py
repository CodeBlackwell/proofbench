"""Config is the entire domain surface. The engine reads only this object."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import runner
from .util import die


@dataclass
class Task:
    name: str
    path: Path           # the repo the agent works in
    invoke: str          # what the agent is asked to do, e.g. "/crg-debug"
    default_branch: str  # the broken / initial state
    answer_branch: str   # the ground-truth fixed state


@dataclass
class QuestionSet:
    name: str
    path: Path           # JSONL, one question per line, with its known answer


@dataclass
class Config:
    root: Path                       # config file's directory; all paths resolve against it
    runner: str
    models: list                     # the subject-driver sweep; the weak leg is the signal
    judge_model: str                 # held constant — never let the weak model grade itself
    synth_model: str
    objective: str
    concurrency: int
    max_turns: int
    judge_prompt: str
    corpus: list = field(default_factory=list)
    runner_args: list = field(default_factory=list)  # flags the arm needs beside --model
    subject: Path = None             # the artifact under optimization; None => pure-eval mode
    synth_prompt: str = None         # presence (with subject) unlocks `optimize`
    kind: str = "repo"               # "repo" grades a diff, "question" grades an answer

    @property
    def can_optimize(self):
        return self.subject is not None and self.synth_prompt is not None


def _question_file(path):
    return path if path.is_file() else die(f"question file not found: {path}")


def _corpus(entries, resolve):
    """One corpus, one kind: a mixed corpus would need two capture paths inside one leg."""
    kinds = {entry.get("kind", "repo") for entry in entries}
    if len(kinds) > 1:
        die(f"corpus mixes task kinds: {sorted(kinds)}")
    kind = kinds.pop()
    if kind == "question":
        return kind, [QuestionSet(name=Path(entry["file"]).stem,
                                  path=_question_file(resolve(entry["file"]))) for entry in entries]
    if kind != "repo":
        die(f"unknown corpus kind: {kind}")
    return kind, [Task(name=entry["name"], path=resolve(entry["path"]), invoke=entry["invoke"],
                       default_branch=entry["default_branch"], answer_branch=entry["answer_branch"])
                  for entry in entries]


def _arm(runner_name, resolve):
    """A question corpus is driven by an executable that reads one question on stdin, so the
    built in claude runner, which drives a repository with an invoke string, cannot serve it."""
    if runner_name in runner.BUILTINS:
        die(f"a question corpus needs an executable runner, not '{runner_name}'")
    arm = resolve(runner_name)
    return str(arm) if arm.is_file() else die(f"runner not found: {arm}")


def _read_runner_args(raw, kind):
    """The flags an arm needs beside --model: which frozen snapshot to read, and whatever
    configuration the arm is measured under. They live in the config so a run records the
    configuration it ran under. A repo task is invoked `<runner> <invoke> <model>`, which has
    nowhere to put them, so carrying them there is a hard stop and never a silent drop."""
    args = raw.get("runner_args") or []
    if not isinstance(args, list) or any(not isinstance(one, str) for one in args):
        die(f"runner_args must be a list of strings, so quote every number: {args!r}")
    if args and kind != "question":
        die(f"runner_args is a question corpus key: a {kind} task has nowhere to put {args}")
    return args


def _build_config(raw, root, resolve, kind, tasks):
    """Every field the engine reads, so load stays the front door: find the file, parse it,
    resolve the corpus."""
    runner_name = raw.get("runner", "claude")
    models = raw.get("models") or die("config has no models")
    return Config(
        root=root,
        runner=_arm(runner_name, resolve) if kind == "question" else runner_name,
        models=models,
        judge_model=raw.get("judge_model", models[0]),
        synth_model=raw.get("synth_model", models[0]),
        objective=raw.get("objective", "macro_recall"),
        concurrency=int(raw.get("concurrency", 3)),
        max_turns=int(raw.get("max_turns", 200)),
        judge_prompt=(resolve(raw.get("judge")) or die("config has no judge prompt")).read_text(),
        corpus=tasks,
        runner_args=_read_runner_args(raw, kind),
        subject=resolve(raw.get("subject")),
        synth_prompt=resolve(raw.get("synth")).read_text() if raw.get("synth") else None,
        kind=kind,
    )


def load(config_path):
    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        die(f"config not found: {path}")
    root = path.parent
    raw = yaml.safe_load(path.read_text()) or {}

    def resolve(value):
        return (root / Path(value).expanduser()).resolve() if value else None

    kind, tasks = _corpus(raw.get("corpus") or die("config has no corpus"), resolve)
    return _build_config(raw, root, resolve, kind, tasks)
