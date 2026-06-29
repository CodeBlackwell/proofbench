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
    match = re.search(r"\{.*\}", result, re.DOTALL)
    if not match:
        die("no JSON object found in LLM result")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        die("LLM result was not valid JSON")


def claude_json(prompt, model):
    """Call claude headless and return the parsed JSON object it produced.

    The prompt goes on STDIN, never argv: an embedded diff can exceed ARG_MAX and
    silently abort exec, which once manufactured a confident wrong number."""
    proc = subprocess.run(
        ["claude", "-p", "--model", model,
         "--dangerously-skip-permissions", "--output-format", "json"],
        input=prompt, capture_output=True, text=True,
    )
    return extract_json(proc.stdout)
