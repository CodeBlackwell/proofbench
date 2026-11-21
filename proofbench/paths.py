"""The path: how a system got to its result, graded beside the result and never mixed into it.

Three graders read a step log. Fixed rules are checked here. A script checks what they cannot
express. A judge reads the path against the owner's rubric, and is shown the task and a
recorded good path when one is kept, but never the answer: what an answer owes to its path is
a rule's business, where it can be checked and not guessed."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import judge, steps
from .util import die, spawn

RULES = ("called", "never_called", "before", "max_steps", "script")
RECORDED = "paths"                 # the folder of recorded good paths, beside the config
ANSWER = {"question": "answer.json", "repo": "agent.diff"}   # what a rule script is handed


@dataclass
class PathSpec:
    rules: list = field(default_factory=list)  # (kind, value) pairs, in the config's order
    judge_prompt: str = None                   # the path rubric; None when rules alone grade


def _is_usable(kind, value):
    if kind == "before":
        return (isinstance(value, list) and len(value) == 2
                and all(isinstance(tool, str) for tool in value))
    if kind == "max_steps":
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    return isinstance(value, str) and bool(value.strip())


def _read_rule(entry, resolve):
    if not isinstance(entry, dict) or len(entry) != 1 or next(iter(entry)) not in RULES:
        die(f"a path rule is one of {list(RULES)} and its value: {entry!r}")
    (kind, value), = entry.items()
    if not _is_usable(kind, value):
        die(f"path rule `{kind}` cannot use the value {value!r}")
    if kind != "script":
        return kind, value
    script = resolve(value)
    if not script.is_file() or not os.access(script, os.X_OK):
        die(f"path rule script is not an executable file: {script}")
    return kind, str(script)


def read(raw, resolve):
    """The `path` key of a config, or None for an eval that grades outcomes alone."""
    spec = raw.get("path")
    if spec is None:
        return None
    if not isinstance(spec, dict) or not spec or set(spec) - {"rules", "judge"}:
        die(f"path takes `rules`, `judge`, or both: {spec!r}")
    rules = spec.get("rules") or []
    if not isinstance(rules, list):
        die(f"path rules must be a list: {rules!r}")
    rubric = resolve(spec.get("judge"))
    if rubric is not None and not rubric.is_file():
        die(f"path judge file not found: {rubric}")
    if not rules and rubric is None:
        die("path names no rule and no judge, so nothing would grade it")
    return PathSpec([_read_rule(entry, resolve) for entry in rules],
                    rubric.read_text() if rubric else None)


def label(kind, value):
    if kind == "script":
        return f"script:{Path(value).name}"
    return f"{kind}:{'>'.join(value) if kind == 'before' else value}"


def _holds(kind, value, tools):
    """One fixed rule against the tools called, in order: whether it held, and if not, why.
    `before: [A, B]` holds when B was never called, or some A came ahead of the first B."""
    if kind == "called":
        return value in tools, f"{value} was never called"
    if kind == "never_called":
        return value not in tools, f"{value} was called"
    if kind == "max_steps":
        return len(tools) <= value, f"{len(tools)} steps, over {value}"
    first, then = value
    is_ordered = then not in tools or first in tools[:tools.index(then)]
    return is_ordered, f"{then} was called with no {first} before it"


def _run_script(script, folder, kind, minutes):
    """Exit 0 holds and exit 1 does not. Anything else is a rule that crashed, and a crash read
    as a failure would blame the system for the rule's own bug, so it is a hard stop."""
    proc = spawn([script, str(folder / steps.FILE), str(folder / ANSWER[kind])], minutes)
    if proc.returncode not in (0, 1):
        said = (proc.stderr or proc.stdout).strip()[:300]
        die(f"path rule {script} exited {proc.returncode} on {folder}: {said}")
    return proc.returncode == 0, (proc.stdout.strip().splitlines() or [""])[0]


def check_rules(cfg, folder, logged):
    """Every rule of the eval against one result: {label: {held, why}}."""
    tools, ruled = [step["tool"] for step in logged], {}
    for kind, value in cfg.path.rules:
        if kind == "script":
            held, why = _run_script(value, folder, cfg.kind, cfg.timeout_minutes)
        else:
            held, why = _holds(kind, value, tools)
        ruled[label(kind, value)] = {"held": held, "why": why if kind == "script" or not held else ""}
    return ruled


def _judge(cfg, task_text, owner, folder):
    """The path judge's verdict on one step log, and what asking cost. A verdict that is not 1
    or 0 is a hard stop, as an empty grade is."""
    example = cfg.root / RECORDED / owner / steps.FILE
    shown = f"===== EXAMPLE_PATH =====\n{example.read_text()}\n\n" if example.is_file() else ""
    prompt = (f"{cfg.path.judge_prompt}\n\n===== TASK =====\n{task_text}\n\n{shown}"
              f"===== AGENT_PATH =====\n{(folder / steps.FILE).read_text()}\n")
    verdict, cost_usd = judge.ask(prompt, cfg.judge_model, cfg.judge_input_limit_kb,
                                  f"the path of {owner}")
    if verdict.get("sound") not in (0, 1):
        die(f"path judge returned no binary 'sound' on {owner}: {verdict}")
    return verdict, cost_usd


def grade(cfg, task_text, owner, folder):
    """The path grade of the result in `folder`, which holds its step log and its answer file.
    Returns the fields the grade gains and what the path judge cost. A run and a control are
    graded through here alike, so a control proves the grader a run will meet."""
    logged, fields, cost_usd = steps.read(folder / steps.FILE), {}, None
    if cfg.path.rules:
        ruled = check_rules(cfg, folder, logged)
        fields.update(rules_held=int(all(one["held"] for one in ruled.values())), rules=ruled)
    if cfg.path.judge_prompt:
        verdict, cost_usd = _judge(cfg, task_text, owner, folder)
        fields.update(path_sound=int(verdict["sound"]), path_why=verdict.get("why", ""))
    return fields, cost_usd
