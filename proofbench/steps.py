"""The step log: what a system did on the way to its result, one step per line.

One format, whatever the system. A line is a JSON object naming the tool that was called, what
it was called with, and what came back. An adapter writes the log to the file its environment
names under PROOFBENCH_STEPS. The built-in claude runner needs no adapter: its steps are read
here from the CLI's own stream. A path graded without its log would be graded as an empty
path, so a missing log is a hard stop, and an adapter whose system called nothing still writes
an empty file."""
import json

from .util import die

ENV = "PROOFBENCH_STEPS"
FILE = "steps.jsonl"
FIELDS = ("tool", "input", "result")


def _read_line(path, number, line):
    try:
        step = json.loads(line)
    except json.JSONDecodeError as err:
        die(f"{path}:{number} is not JSON: {err}")
    is_step = (isinstance(step, dict) and isinstance(step.get("tool"), str)
               and all(name in step for name in FIELDS))
    return step if is_step else die(f"{path}:{number} is not a step: it needs {list(FIELDS)}")


def read(path):
    """Every step of one log, in the order it was taken."""
    if not path.is_file():
        die(f"no step log at {path}: the adapter writes one to ${ENV}, even when it is empty")
    lines = enumerate(path.read_text().splitlines(), 1)
    return [_read_line(path, number, line) for number, line in lines if line.strip()]


def write(path, steps):
    path.write_text("".join(json.dumps(step) + "\n" for step in steps))


def events(stream):
    """The JSON events of a `claude --output-format stream-json` transcript. Hooks and plugins
    print lines of their own into the same stream, so a line that is not an event is skipped."""
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def _blocks(stream, kind):
    for event in events(stream):
        content = (event.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == kind:
                yield block


def _text(content):
    """A tool's result as one string: the CLI sends a string, or a list of blocks."""
    if isinstance(content, list):
        return "\n".join(block.get("text", json.dumps(block)) for block in content)
    return content


def from_claude(stream):
    """The steps in a claude transcript, written against the stream of CLI 2.1.319: a call is a
    `tool_use` block in an assistant event, and its result a `tool_result` block in a later
    user event carrying the call's id. A subagent's calls are in the same stream and are kept
    in the order they arrived. A call the run was cut off before answering has result null."""
    results = {block["tool_use_id"]: _text(block.get("content"))
               for block in _blocks(stream, "tool_result")}
    return [{"tool": call["name"], "input": call["input"], "result": results.get(call["id"])}
            for call in _blocks(stream, "tool_use")]
