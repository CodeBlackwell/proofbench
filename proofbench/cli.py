"""proofbench {run|optimize} — config-driven eval and self-improvement for agent skills."""
import argparse
import sys
import time
from pathlib import Path

from . import __version__, config, engine, optimize
from .util import HarnessError, die, log

DEMO = Path(__file__).resolve().parent.parent / "examples" / "proofbench.demo.yaml"
# stubbed and is_measured lead, so the one line a reader takes away from a run says whether the
# numbers behind it were measured at all, and measures says which numbers they are. A leg carries
# either the accuracy names or the abstention names, never both, so the line prints what is there.
HEADLINE = ("stubbed", "is_measured", "measures", "questions", "trials", "answerable",
            "unanswerable", "accuracy", "abstention_rate", "non_abstention_rate_answerable",
            "abstention_correct_unanswerable", "tokens_total", "tokens_per_correct",
            "tokens_per_correct_abstention", "unstable_questions")


def _config_path(args):
    if args.demo:
        return DEMO if DEMO.is_file() else sys.exit("--demo needs a source checkout; pass --config")
    return args.config or sys.exit("pass --config PATH (or --demo)")


def _report_questions(model, leg):
    """The headline numbers, then the pass^k and pass@k curve: a leg that is right on average
    and a leg that is right every time are different legs."""
    log(f"[{model}] {({key: leg[key] for key in HEADLINE if key in leg})}")
    log(f"[{model}] {({key: leg[key] for key in leg if 'pass^' in key or 'pass@' in key})}")


def run_dir(run_id):
    """Where this run writes. A folder is never reused: what an earlier run left in it would be
    read as this run's, and optimize would learn from grades of tasks no longer in the corpus.
    With no --run-id the folder is named for the moment the run started."""
    chosen = Path("runs") / (run_id or time.strftime("%Y%m%d-%H%M%S"))
    while run_id is None and chosen.exists():
        chosen = chosen.with_name(chosen.name + "+")
    if chosen.exists() and any(chosen.iterdir()):
        die(f"{chosen} already holds a run; pass another --run-id or remove it")
    log(f"writing to {chosen}")
    return chosen


def cmd_run(cfg, args):
    board = engine.bench(cfg, run_dir(args.run_id), cfg.models)
    for model, leg in board.items():
        if cfg.kind == "question":
            _report_questions(model, leg)
            continue
        macro = {k: round(v, 3) for k, v in leg.items() if k.startswith("macro_")}
        log(f"[{model}] {macro}")


def cmd_optimize(cfg, args):
    optimize.optimize(cfg, run_dir(args.run_id))


def main():
    parser = argparse.ArgumentParser(prog="proofbench")
    parser.add_argument("--version", action="version", version=f"proofbench {__version__}")
    parser.add_argument("command", choices=["run", "optimize"])
    parser.add_argument("--config")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--run-id", help="folder under runs/; defaults to the start time")
    args = parser.parse_args()
    try:
        cfg = config.load(_config_path(args))
        (cmd_run if args.command == "run" else cmd_optimize)(cfg, args)
    except HarnessError as err:
        print(f"\033[31m[proofbench] {err}\033[0m", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
