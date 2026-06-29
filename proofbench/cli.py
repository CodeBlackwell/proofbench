"""proofbench {run|optimize} — config-driven eval and self-improvement for agent skills."""
import argparse
import sys
from pathlib import Path

from . import config, engine, optimize
from .util import HarnessError, log

DEMO = Path(__file__).resolve().parent.parent / "examples" / "proofbench.demo.yaml"


def _config_path(args):
    if args.demo:
        return DEMO if DEMO.is_file() else sys.exit("--demo needs a source checkout; pass --config")
    return args.config or sys.exit("pass --config PATH (or --demo)")


def cmd_run(cfg, args):
    board = engine.bench(cfg, Path("runs") / args.run_id, cfg.models)
    for model, leg in board.items():
        macro = {k: round(v, 3) for k, v in leg.items() if k.startswith("macro_")}
        log(f"[{model}] {macro}")


def cmd_optimize(cfg, args):
    optimize.optimize(cfg, Path("runs") / args.run_id)


def main():
    parser = argparse.ArgumentParser(prog="proofbench")
    parser.add_argument("command", choices=["run", "optimize"])
    parser.add_argument("--config")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--run-id", default="run")
    args = parser.parse_args()
    try:
        cfg = config.load(_config_path(args))
        (cmd_run if args.command == "run" else cmd_optimize)(cfg, args)
    except HarnessError as err:
        print(f"\033[31m[proofbench] {err}\033[0m", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
