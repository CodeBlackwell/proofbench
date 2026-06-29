"""Config is the entire domain surface. The engine reads only this object."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .util import die


@dataclass
class Task:
    name: str
    path: Path           # the repo the agent works in
    invoke: str          # what the agent is asked to do, e.g. "/crg-debug"
    default_branch: str  # the broken / initial state
    answer_branch: str   # the ground-truth fixed state


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
    subject: Path = None             # the artifact under optimization; None => pure-eval mode
    synth_prompt: str = None         # presence (with subject) unlocks `optimize`

    @property
    def can_optimize(self):
        return self.subject is not None and self.synth_prompt is not None


def load(config_path):
    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        die(f"config not found: {path}")
    root = path.parent
    raw = yaml.safe_load(path.read_text()) or {}

    def resolve(value):
        return (root / Path(value).expanduser()).resolve() if value else None

    corpus = raw.get("corpus") or die("config has no corpus")
    tasks = [Task(name=t["name"], path=resolve(t["path"]), invoke=t["invoke"],
                  default_branch=t["default_branch"], answer_branch=t["answer_branch"])
             for t in corpus]

    models = raw.get("models") or die("config has no models")
    return Config(
        root=root,
        runner=raw.get("runner", "claude"),
        models=models,
        judge_model=raw.get("judge_model", models[0]),
        synth_model=raw.get("synth_model", models[0]),
        objective=raw.get("objective", "macro_recall"),
        concurrency=int(raw.get("concurrency", 3)),
        max_turns=int(raw.get("max_turns", 200)),
        judge_prompt=(resolve(raw.get("judge")) or die("config has no judge prompt")).read_text(),
        corpus=tasks,
        subject=resolve(raw.get("subject")),
        synth_prompt=resolve(raw.get("synth")).read_text() if raw.get("synth") else None,
    )
