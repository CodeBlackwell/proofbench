"""Runner adapters: how the subject is driven headless. Driver-agnostic by design.

A built-in name (``claude``) maps to a command builder. Any other value is treated as
a path to an executable. A repo task invokes it as ``<runner> <invoke> <model>``; a question
task hands it one question on stdin and reads one result object back."""
import json
import time
from pathlib import Path

from .util import die, spawn

_NO_META = {"cost_usd": None, "turns": None, "tokens_in": None, "tokens_out": None}

# The result fields the question grade and the headline metric are computed from. The rest of
# the arm contract (answer, cost_usd, seconds, chunks, path) is logged, never required here.
# Each is held to its type: the string "false" is true, and it would grade as an abstention.
_NEEDED = {"answer_ids": list, "abstained": bool, "tokens_in": (int, float),
           "tokens_out": (int, float)}

# All an arm is handed. The rest of a question record is the answer key, or a note the corpus
# keeps on it (answerable, type, evidence), and an arm that passed any of that on to a model
# would be graded against a key it had been shown.
_ASKED = ("id", "text")


def _claude(invoke, model, max_turns):
    return ["claude", "-p", invoke, "--model", model,
            "--dangerously-skip-permissions", "--output-format", "json",
            "--max-turns", str(max_turns)]


BUILTINS = {"claude": _claude}


def _claude_meta(stdout):
    """Pull cost, turns and token usage from a ``claude --output-format json`` envelope.
    Observability for the repo task, so this never dies: a custom runner or malformed
    envelope yields None and the wall-clock seconds still stand. The question task does not
    read this; it takes its token counts from the arm's own result object, which it requires."""
    try:
        envelope = json.loads(stdout[stdout.index("{"):stdout.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return dict(_NO_META)
    usage = envelope.get("usage") or {}
    return {"cost_usd": envelope.get("total_cost_usd"), "turns": envelope.get("num_turns"),
            "tokens_in": usage.get("input_tokens"), "tokens_out": usage.get("output_tokens")}


def run(runner, invoke, model, max_turns, cwd, log_path, timeout_minutes=None):
    """Execute one headless attempt in ``cwd``; capture all output to ``log_path`` and
    return its ``{seconds, cost_usd, turns, tokens_in, tokens_out}``.

    The agent's exit status is advisory: what gets graded is the artifact it leaves
    behind (see capture), never the agent's own claim of success."""
    argv = BUILTINS[runner](invoke, model, max_turns) if runner in BUILTINS \
        else [runner, invoke, model]
    start = time.time()
    proc = spawn(argv, timeout_minutes, cwd=cwd)
    Path(log_path).write_text(proc.stdout + proc.stderr)
    meta = _claude_meta(proc.stdout) if runner in BUILTINS else dict(_NO_META)
    return {"seconds": round(time.time() - start, 1), **meta}


def _is(value, kind):
    """True is an int to Python, and a token count of True is not a count."""
    return isinstance(value, kind) and (kind is bool or not isinstance(value, bool))


def ask(arm, model, question, log_path, runner_args=(), timeout_minutes=None):
    """Drive one question through an arm executable: the question's id and text go in on stdin,
    one result object comes back on stdout. Unlike a repo task, the arm's exit status is not
    advisory: there is no artifact left behind to grade, so a failed arm has to be fatal.

    ``runner_args`` is the config's own argv for this arm, appended after --model MODEL. An arm
    that needs to be told which frozen corpus to read cannot start without it, and reading it
    off the config is what makes the run reproducible from the config alone."""
    asked = {field: question[field] for field in _ASKED}
    proc = spawn([str(arm), "--model", model, *runner_args], timeout_minutes,
                 input=json.dumps(asked))
    Path(log_path).write_text(proc.stdout + proc.stderr)
    if proc.returncode != 0:
        die(f"arm exited {proc.returncode} on {question['id']}: {proc.stderr.strip()[:300]}")
    try:
        result = json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        die(f"arm printed no result object on {question['id']}: {proc.stdout.strip()[:300]}")
    if not isinstance(result, dict):
        die(f"arm printed no result object on {question['id']}: {proc.stdout.strip()[:300]}")
    wrong = [field for field, kind in _NEEDED.items() if not _is(result.get(field), kind)]
    if wrong:
        die(f"arm result on {question['id']} is missing or mistypes {wrong}")
    return result
