"""Fail-loud helpers. The measurement system must crash on bad data, never average around it."""
import json
import re
import subprocess
import sys


class HarnessError(RuntimeError):
    """A measurement failed. Always fatal — never swallowed into a plausible number."""


def die(message):
    raise HarnessError(message)


def log(message):
    print(f"\033[36m[proofbench]\033[0m {message}", file=sys.stderr)


def spawn(argv, minutes=None, **kwargs):
    """Start a child and wait for it. A child that cannot start, or that outlives its limit, is
    a failed measurement: it is said in one line, and the run never waits on it for ever. Bytes
    that are not UTF-8 are replaced, never raised on, because a diff or a log may hold any."""
    try:
        return subprocess.run(argv, capture_output=True, text=True, errors="replace",
                              timeout=minutes * 60 if minutes else None, **kwargs)
    except OSError as err:
        die(f"cannot start {argv[0]}: {err}")
    except subprocess.TimeoutExpired:
        die(f"{argv[0]} ran past its limit of {minutes} minutes")


def _refuse_constant(name):
    die(f"LLM result holds {name}, which is not a number a grade can carry")


def extract_json(envelope):
    """Parse a `claude --output-format json` envelope's `.result`, tolerant of a prose
    preamble or markdown fences by slicing the first '{' to the last '}'. Fail loud at
    every step so a narrating model can never yield an empty grade that flows onward."""
    if not envelope.strip():
        die("LLM produced no output")
    try:
        result = json.loads(envelope)["result"]
    except (json.JSONDecodeError, KeyError, TypeError):
        die("LLM envelope was not valid `--output-format json`")
    match = re.search(r"\{.*\}", result, re.DOTALL) if isinstance(result, str) else None
    if not match:
        die("no JSON object found in LLM result")
    try:
        return json.loads(match.group(0), parse_constant=_refuse_constant)
    except json.JSONDecodeError:
        die("LLM result was not valid JSON")


# A judge or synth call is one reply with no tools, so a quarter of an hour means it hung.
CLAUDE_MINUTES = 15


def sum_reported(costs):
    """None, never zero, when nothing reported a cost: unreported and free are different facts."""
    reported = [cost for cost in costs if cost is not None]
    return round(sum(reported), 6) if reported else None


def _read_cost(envelope):
    try:
        return json.loads(envelope).get("total_cost_usd")
    except (json.JSONDecodeError, AttributeError):
        return None


def claude_json(prompt, model):
    """Ask claude for one JSON object, and ask once more if the first reply was not one. A
    judge that narrated instead of grading has produced nothing to average around, so asking
    again changes no number, and it keeps one flake from costing a whole leg of agent runs.

    Returns the object and what the asking cost in USD. A first reply that could not be used
    was still paid for, so it is counted."""
    spent = []
    try:
        return _ask_claude(prompt, model, spent), sum_reported(spent)
    except HarnessError as first:
        log(f"claude gave no usable object ({first}); asking once more")
        return _ask_claude(prompt, model, spent), sum_reported(spent)


def _ask_claude(prompt, model, spent):
    """Call claude headless and return the parsed JSON object it produced, noting what the call
    cost in ``spent`` before the reply is parsed.

    The prompt goes on STDIN, never argv: an embedded diff can exceed ARG_MAX and
    silently abort exec, which once manufactured a confident wrong number.

    The judge and the synth read text an agent wrote and answer with one object, so they get no
    tools (--tools "") and none of the launching user's CLAUDE.md, hooks, plugins or MCP servers
    (--safe-mode). A grade must not depend on where proofbench was started, and a diff must not
    be able to instruct a process that can act."""
    proc = spawn(
        ["claude", "-p", "--model", model, "--tools", "", "--safe-mode", "--output-format", "json"],
        CLAUDE_MINUTES, input=prompt)
    if proc.returncode != 0:
        die(f"claude exited {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:300]}")
    spent.append(_read_cost(proc.stdout))
    return extract_json(proc.stdout)
