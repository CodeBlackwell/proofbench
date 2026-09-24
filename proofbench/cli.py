"""proofbench {run|optimize} — config-driven eval and self-improvement for agent skills."""
import argparse
import sys
from pathlib import Path

from . import config, engine, optimize, scoreboard
from .util import HarnessError, log

DEMO = Path(__file__).resolve().parent.parent / "examples" / "proofbench.demo.yaml"
# stubbed and is_measured lead, so the one line a reader takes away from a run says whether the
# numbers behind it were measured at all, and measures says which numbers they are. A leg carries
# either the accuracy names or the abstention names, never both, so the line prints what is there.
HEADLINE = ("stubbed", "is_measured", "measures", "questions", "answerable", "unanswerable",
            "accuracy", "abstention_rate", "non_abstention_rate_answerable",
            "abstention_correct_unanswerable", "tokens_total", "tokens_per_correct",
            "tokens_per_correct_abstention")


def _config_path(args):
    if args.demo:
        return DEMO if DEMO.is_file() else sys.exit("--demo needs a source checkout; pass --config")
    return args.config or sys.exit("pass --config PATH (or --demo)")


def _report_questions(model, leg):
    """The headline numbers, then the grid the study reads them in: tier by hop depth. The grid
    prints whichever rate the leg could honestly produce, so a corpus that measured only
    abstention prints a grid of abstention rates under that heading and no other."""
    log(f"[{model}] {({key: leg[key] for key in HEADLINE if key in leg})}")
    metric = "accuracy" if "accuracy" in leg else "abstention_rate"
    print(scoreboard.grid(leg["records"], "tier", "hops", metric), file=sys.stderr)


def cmd_run(cfg, args):
    board = engine.bench(cfg, Path("runs") / args.run_id, cfg.models)
    for model, leg in board.items():
        if cfg.kind == "question":
            _report_questions(model, leg)
            continue
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
