"""Runner adapters: how the subject is driven headless. Driver-agnostic by design.

A built-in name (``claude``) maps to a command builder. Any other value is treated as
a path to an executable invoked as ``<runner> <invoke> <model>`` — bring your own agent."""
import json
import subprocess
import time


def _claude(invoke, model, max_turns):
    return ["claude", "-p", invoke, "--model", model,
            "--dangerously-skip-permissions", "--output-format", "json",
            "--max-turns", str(max_turns)]


BUILTINS = {"claude": _claude}


def _claude_meta(stdout):
    """Pull cost + turns from a ``claude --output-format json`` envelope. Observability,
    not a graded metric, so this never dies: a custom runner or malformed envelope yields
    None and the wall-clock seconds still stand."""
    try:
        env = json.loads(stdout[stdout.index("{"):stdout.rindex("}") + 1])
        return env.get("total_cost_usd"), env.get("num_turns")
    except (ValueError, json.JSONDecodeError):
        return None, None


def run(runner, invoke, model, max_turns, cwd, log_path):
    """Execute one headless attempt in ``cwd``; capture all output to ``log_path`` and
    return its ``{seconds, cost_usd, turns}``.

    The agent's exit status is advisory — what gets graded is the artifact it leaves
    behind (see capture), never the agent's own claim of success."""
    argv = BUILTINS[runner](invoke, model, max_turns) if runner in BUILTINS \
        else [runner, invoke, model]
    start = time.time()
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    open(log_path, "w").write(proc.stdout + proc.stderr)
    cost, turns = _claude_meta(proc.stdout) if runner in BUILTINS else (None, None)
    return {"seconds": round(time.time() - start, 1), "cost_usd": cost, "turns": turns}
