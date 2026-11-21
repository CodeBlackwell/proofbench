"""Config is the entire domain surface. The engine reads only this object.

Whatever a run would trip over later is refused here, before an agent or a judge is paid for."""
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import objective, paths, runner
from .corpus import QuestionSet, Task, _strings, read_corpus  # noqa: F401 (read as config.Task)
from .util import die

# Every key a config may carry. A misspelt key is silently its default, and `judge_modle` once
# left the weak model grading itself, so a key outside this set is a hard stop.
KEYS = {"runner", "models", "judge_model", "synth_model", "objective", "concurrency",
        "max_turns", "judge", "subject", "synth", "corpus", "runner_args", "trials",
        "timeout_minutes", "judge_input_limit_kb", "classes", "path"}


@dataclass
class Config:
    root: Path                       # config file's directory; all paths resolve against it
    runner: str
    models: list                     # the subject-driver sweep; the weak leg is the signal
    judge_model: str                 # held constant — never let the weak model grade itself
    synth_model: str
    objective: str                   # None on a question corpus that only ever runs
    concurrency: int
    max_turns: int
    judge_prompt: str
    corpus: list = field(default_factory=list)
    runner_args: list = field(default_factory=list)  # flags the arm needs beside --model
    subject: Path = None             # the artifact under optimization; None => pure-eval mode
    synth_prompt: str = None         # presence (with subject) unlocks `optimize`
    kind: str = "repo"               # "repo" grades a diff, "question" grades an answer
    trials: int = 1                  # times each question is asked; pass^k and pass@k read them
    timeout_minutes: float = None    # the longest one agent or arm attempt may run; None waits
    judge_input_limit_kb: float = 200  # the largest prompt a judge is sent; over it the run stops
    classes: list = field(default_factory=list)  # the answer classes the coverage gate counts
    path: paths.PathSpec = None      # how the path is graded; None grades outcomes alone
    file: Path = None                # the config file itself, which every gate's hash covers
    checked: bool = False            # the gates passed on this eval as it stands; set by the CLI

    @property
    def can_optimize(self):
        return self.subject is not None and self.synth_prompt is not None


def _arm(runner_name, resolve):
    """A question corpus is driven by an executable that reads one question on stdin, so the
    built in claude runner, which drives a repository with an invoke string, cannot serve it."""
    if runner_name in runner.BUILTINS:
        die(f"a question corpus needs an executable runner, not '{runner_name}'")
    arm = resolve(runner_name)
    if not arm.is_file():
        die(f"runner not found: {arm}")
    return str(arm) if os.access(arm, os.X_OK) else die(f"runner is not executable: {arm}")


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


def _read_count(raw, key, default):
    count = raw.get(key, default)
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        die(f"{key} must be a whole number of at least 1: {count!r}")
    return count


def _read_models(raw):
    """`models: haiku` is a string, and a string iterates into five legs named h, a, i, k, u."""
    models = raw.get("models")
    if not isinstance(models, list) or not models or any(not isinstance(m, str) for m in models):
        die(f"models must be a list of model names: {models!r}")
    return models


def _read_positive(raw, key, default=None):
    number = raw.get(key, default)
    if number is None:
        return None
    if isinstance(number, bool) or not isinstance(number, (int, float)) or number <= 0:
        die(f"{key} must be a number above 0: {number!r}")
    return number


def _read_file(raw, key, resolve):
    """A file the config names has to exist now: a missing subject used to be found only after
    the baseline had run."""
    path = resolve(raw.get(key))
    return path if path is None or path.is_file() else die(f"{key} file not found: {path}")


def _read_prompt(raw, key, resolve, kind):
    """`default` names the prompt proofbench ships inside the package, so an installed copy has
    one. It ships them for a repo task only: an answer rubric knows the domain it grades."""
    if raw.get(key) != "default":
        path = _read_file(raw, key, resolve)
        return path.read_text() if path else None
    if kind != "repo":
        die(f"{key}: default is the repo task's prompt; a {kind} corpus has to bring its own")
    return (Path(__file__).parent / "prompts" / f"{key}.md").read_text()


def _read_trials(raw, kind):
    """How many times each question is asked. pass^k and pass@k count right and wrong attempts,
    and only a question task grades an attempt right or wrong: a repo task is graded on the
    judge's numeric fields, so trials there is a hard stop and never a silent single run."""
    trials = _read_count(raw, "trials", 1)
    if trials > 1 and kind != "question":
        die(f"trials is a question corpus key: a {kind} task has no pass or fail to count")
    return trials


def _read_judge(raw, resolve, kind, tasks):
    """A repo corpus graded by command alone is sent to no judge, so it needs no rubric. Nor
    does a question corpus whose answers are ids from a fixed list: left without a `judge`,
    it is graded by exact match alone, and an id that does not match is wrong."""
    is_judged = kind == "repo" and any(not task.check for task in tasks)
    prompt = _read_prompt(raw, "judge", resolve, kind)
    return prompt if prompt or not is_judged else die("config has no judge prompt")


def _build_config(raw, path, resolve, kind, tasks):
    """Every field the engine reads, so load stays the front door: find the file, parse it,
    resolve the corpus."""
    runner_name = raw.get("runner", "claude")
    models = _read_models(raw)
    trials = _read_trials(raw, kind)
    graded_by_command = kind == "repo" and all(task.check for task in tasks)
    return Config(
        root=path.parent, file=path,
        runner=_arm(runner_name, resolve) if kind == "question" else runner_name,
        models=models,
        judge_model=raw.get("judge_model", models[0]),
        synth_model=raw.get("synth_model", models[0]),
        objective=objective.read(raw, kind, trials,
                                 "macro_passed" if graded_by_command else "macro_recall"),
        concurrency=_read_count(raw, "concurrency", 3),
        max_turns=_read_count(raw, "max_turns", 200),
        judge_prompt=_read_judge(raw, resolve, kind, tasks),
        corpus=tasks,
        runner_args=_read_runner_args(raw, kind),
        subject=_read_file(raw, "subject", resolve),
        synth_prompt=_read_prompt(raw, "synth", resolve, kind),
        kind=kind, trials=trials, timeout_minutes=_read_positive(raw, "timeout_minutes"),
        judge_input_limit_kb=_read_positive(raw, "judge_input_limit_kb", 200),
        classes=_strings(raw, "classes"), path=paths.read(raw, resolve),
    )


def _parse(path):
    """The config as a mapping of known keys, or a hard stop that names what is wrong with it."""
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as err:
        die(f"config is not valid YAML: {err}")
    if not isinstance(raw, dict):
        die(f"config must be a mapping of keys: {path}")
    unknown = sorted(set(raw) - KEYS)
    return raw if not unknown else die(f"config has keys proofbench does not read: {unknown}")


def load(config_path):
    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        die(f"config not found: {path}")
    root = path.parent
    raw = _parse(path)

    def resolve(value):
        return (root / Path(value).expanduser()).resolve() if value else None

    kind, tasks = read_corpus(raw.get("corpus") or die("config has no corpus"), resolve)
    return _build_config(raw, path, resolve, kind, tasks)
