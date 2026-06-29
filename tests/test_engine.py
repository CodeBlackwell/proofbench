"""End-to-end engine wiring (ground truth -> reset -> run -> capture -> judge -> scoreboard),
exercised with a stub runner and stub judge so it needs no `claude`. Requires the demo corpus:
run `bash examples/sample-corpus/build.sh` first."""
import json
from pathlib import Path

import pytest

from proofbench import config, engine, judge, runner

DEMO = Path(__file__).resolve().parent.parent / "examples" / "proofbench.demo.yaml"
FIXED = "def is_prime(n):\n    return n > 1 and all(n % i for i in range(2, int(n ** 0.5) + 1))\n"


@pytest.mark.skipif(not (DEMO.parent / "sample-corpus/repos/primes").exists(),
                    reason="run examples/sample-corpus/build.sh first")
def test_bench_wires_end_to_end(tmp_path, monkeypatch):
    cfg = config.load(DEMO)

    # stub runner: a "perfect agent" that applies a correct fix to lib.py in the repo
    def fake_run(runner_name, invoke, model, max_turns, cwd, log_path):
        (Path(cwd) / "lib.py").write_text(FIXED)
        Path(log_path).write_text("stub")
    monkeypatch.setattr(runner, "run", fake_run)

    # stub judge: credit recall when the agent actually changed something
    def fake_grade(prompt, readme, answer, agent_diff, model):
        return {"recall": 1.0 if agent_diff.strip() else 0.0, "precision": 1.0}
    monkeypatch.setattr(judge, "grade", fake_grade)

    board = engine.bench(cfg, tmp_path, cfg.models)
    leg = board[cfg.models[0]]
    assert leg["macro_recall"] == 1.0
    assert leg["macro_precision"] == 1.0
    saved = json.loads((tmp_path / "scoreboard.json").read_text())
    assert set(saved[cfg.models[0]]["tasks"]) == {"primes", "ranges"}
