"""proofbench {run|optimize|controls|check|status}: build an eval, check it, then run it."""
import argparse
import sys
import time
from pathlib import Path

from . import __version__, config, controls, engine, gates, optimize
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


def _admit(cfg, args):
    """Scores are produced only by an eval that passed its gates, unless the caller says
    otherwise, and then every scoreboard says so."""
    if args.unchecked:
        log("\033[33mrunning unchecked: this eval has not passed its gates, and every "
            "scoreboard it writes says so\033[0m")
        return
    gates.refuse_unchecked(cfg)
    cfg.checked = True


def cmd_run(cfg, args):
    _admit(cfg, args)
    board = engine.bench(cfg, run_dir(args.run_id), cfg.models)
    for model, leg in board.items():
        if cfg.kind == "question":
            _report_questions(model, leg)
            continue
        macro = {k: round(v, 3) for k, v in leg.items() if k.startswith("macro_")}
        log(f"[{model}] {macro}")


def cmd_optimize(cfg, args):
    _admit(cfg, args)
    optimize.optimize(cfg, run_dir(args.run_id))


def cmd_controls(cfg, args):
    log(f"wrote {controls.build(cfg)} controls and their predictions to {controls.folder(cfg)}")


def cmd_check(cfg, args):
    if args.gate is None:
        die(f"name the gate to check: {', '.join(gates.GATES)}")
    if not gates.check(cfg, args.gate, run_dir(args.run_id)):
        sys.exit(1)


def cmd_status(cfg, args):
    states = gates.status(cfg)
    for gate, state in states.items():
        print(f"{gate:9} {state}")
    sys.exit(0 if set(states.values()) == {"passed"} else 1)


COMMANDS = {"run": cmd_run, "optimize": cmd_optimize, "controls": cmd_controls,
            "check": cmd_check, "status": cmd_status}


def main():
    parser = argparse.ArgumentParser(prog="proofbench")
    parser.add_argument("--version", action="version", version=f"proofbench {__version__}")
    parser.add_argument("command", choices=list(COMMANDS))
    parser.add_argument("gate", nargs="?", choices=gates.GATES, help="for `check`")
    parser.add_argument("--config")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--run-id", help="folder under runs/; defaults to the start time")
    parser.add_argument("--unchecked", action="store_true",
                        help="run an eval that has not passed its gates")
    args = parser.parse_args()
    try:
        cfg = config.load(_config_path(args))
        COMMANDS[args.command](cfg, args)
    except HarnessError as err:
        print(f"\033[31m[proofbench] {err}\033[0m", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
