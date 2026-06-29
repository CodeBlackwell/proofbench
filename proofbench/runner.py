"""Runner adapters: how the subject is driven headless. Driver-agnostic by design.

A built-in name (``claude``) maps to a command builder. Any other value is treated as
a path to an executable invoked as ``<runner> <invoke> <model>`` — bring your own agent."""
import subprocess


def _claude(invoke, model, max_turns):
    return ["claude", "-p", invoke, "--model", model,
            "--dangerously-skip-permissions", "--output-format", "json",
            "--max-turns", str(max_turns)]


BUILTINS = {"claude": _claude}


def run(runner, invoke, model, max_turns, cwd, log_path):
    """Execute one headless attempt in ``cwd``; capture all output to ``log_path``.

    The agent's exit status is advisory — what gets graded is the artifact it leaves
    behind (see capture), never the agent's own claim of success."""
    argv = BUILTINS[runner](invoke, model, max_turns) if runner in BUILTINS \
        else [runner, invoke, model]
    with open(log_path, "w") as log:
        subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, text=True)
