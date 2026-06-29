"""The self-improving loop: synth an improved subject, keep it only if the objective holds.

The keep/revert gate is deterministic and harness-owned. The model proposes; the shell's
comparison decides. A claim the model cannot make is a claim it cannot fake."""
import json
import shutil

from . import engine
from .util import claude_json, die, log


def _collect_grades(run_dir, model):
    blocks = []
    for task_dir in sorted((run_dir / model).iterdir()):
        grade = task_dir / "grade.json"
        if grade.is_file():
            blocks.append(f"--- {task_dir.name} ---\n{grade.read_text()}")
    return "\n".join(blocks)


def _synth(cfg, run_dir, model):
    prompt = (f"{cfg.synth_prompt}\n\n"
              f"===== GRADES =====\n{_collect_grades(run_dir, model)}\n\n"
              f"===== CURRENT_SUBJECT =====\n{cfg.subject.read_text()}\n")
    result = claude_json(prompt, cfg.synth_model)
    candidate = result.get("subject") or die("synth produced no subject")
    (run_dir / "subject.candidate").write_text(candidate)
    (run_dir / "changelog.md").write_text(result.get("changelog", ""))
    return candidate


def optimize(cfg, run_dir):
    if not cfg.can_optimize:
        die("optimize needs both `subject` and `synth` in config")
    model = cfg.models[-1]  # the weak leg is the optimization target — only misses teach
    log(f"baseline on weak leg [{model}]")
    baseline = engine.bench(cfg, run_dir / "baseline", [model])[model]
    base_score = engine.objective_of(baseline, cfg.objective)

    log("synthesizing an improved subject from the misses")
    candidate = _synth(cfg, run_dir, model)
    backup = run_dir / "subject.bak"
    shutil.copy(cfg.subject, backup)
    cfg.subject.write_text(candidate)

    log("re-running with the candidate subject")
    improved = engine.bench(cfg, run_dir / "improved", [model])[model]
    imp_score = engine.objective_of(improved, cfg.objective)

    kept = imp_score >= base_score
    if not kept:
        shutil.copy(backup, cfg.subject)
    verdict = "KEPT" if kept else "REVERTED"
    log(f"{cfg.objective}: baseline={base_score:.3f} improved={imp_score:.3f} -> {verdict}")
    (run_dir / "result.json").write_text(json.dumps(
        {"objective": cfg.objective, "baseline": base_score,
         "improved": imp_score, "kept": kept}, indent=2))
    return kept
