"""The self-improving loop: synth an improved subject, keep it only if the objective improves.

The keep/revert gate is deterministic and harness-owned. The model proposes; the shell's
comparison decides. A claim the model cannot make is a claim it cannot fake.

The synth learns from one part of the corpus and the gate scores on another, the entries marked
`holdout: true`. The synth is shown the expected answers, so a rewrite scored on those same
entries could pass by memorising them, and the gate would have measured its memory."""
import json
import shutil
from dataclasses import replace

from . import engine, question
from .util import claude_json, die, log

# The objectives where the smaller number is the better one. Every other objective is a rate,
# a recall or a pass^k, where larger is better.
LOWER_IS_BETTER = {"tokens_per_correct", "tokens_per_correct_abstention"}


def _collect_grades(cfg, run_dir, model, leg):
    """What the synth reads. A repo task left a grade.json per task. A question task left its
    grades in the leg's records, and only the questions it got wrong are worth showing."""
    if cfg.kind == "question":
        return question.describe_misses(leg["records"])
    blocks = []
    for task_dir in sorted((run_dir / model).iterdir()):
        grade = task_dir / "grade.json"
        if grade.is_file():
            blocks.append(f"--- {task_dir.name} ---\n{grade.read_text()}")
    return "\n".join(blocks)


def _improved(objective, base_score, new_score):
    """The gate. A candidate is kept only when the objective is strictly better, read in the
    direction that objective runs: a lower token price is better, a lower pass rate is not. A
    tie is reverted, or a rewrite that changed nothing would be reported as an improvement."""
    if objective in LOWER_IS_BETTER:
        return new_score < base_score
    return new_score > base_score


def _synth(cfg, run_dir, model, leg):
    grades = _collect_grades(cfg, run_dir / "baseline", model, leg) or die(
        "the baseline left no grades to learn from, so there is nothing to rewrite the subject on")
    prompt = (f"{cfg.synth_prompt}\n\n"
              f"===== GRADES =====\n{grades}\n\n"
              f"===== CURRENT_SUBJECT =====\n{cfg.subject.read_text()}\n")
    result, _ = claude_json(prompt, cfg.synth_model)
    candidate, changelog = result.get("subject"), result.get("changelog", "")
    if not isinstance(candidate, str) or not candidate.strip():
        die("synth produced no subject")
    (run_dir / "subject.candidate").write_text(candidate)
    (run_dir / "changelog.md").write_text(
        changelog if isinstance(changelog, str) else json.dumps(changelog, indent=2))
    return candidate


def _try_candidate(cfg, run_dir, model, candidate, base_score):
    """Install the candidate, score it, and put the original back unless the gate kept it. The
    restore sits in a finally because the re-run is where a run dies: a crash, a Ctrl-C or an
    objective the candidate left undefined would otherwise leave an unvalidated rewrite in the
    live subject file."""
    backup = run_dir / "subject.bak"
    shutil.copy(cfg.subject, backup)
    kept = False
    try:
        cfg.subject.write_text(candidate)
        log("re-running with the candidate subject")
        improved = engine.bench(cfg, run_dir / "improved", [model])[model]
        imp_score = engine.objective_of(improved, cfg.objective)
        kept = _improved(cfg.objective, base_score, imp_score)
    finally:
        if not kept:
            shutil.copy(backup, cfg.subject)
    return imp_score, kept


def _split(cfg):
    """The config twice: once over the entries the synth learns from, once over the held-out
    entries the gate scores on. Both sides have to hold something, and no question may sit on
    both, which the check of the whole corpus refuses as a shared id."""
    if not cfg.can_optimize:
        die("optimize needs both `subject` and `synth` in config")
    if cfg.objective is None:
        die("optimize needs an `objective` in config: the number the gate compares")
    held = [task for task in cfg.corpus if task.holdout]
    learned = [task for task in cfg.corpus if not task.holdout]
    if not held or not learned:
        die("optimize needs corpus entries on both sides of the split: mark the ones the gate "
            "scores on `holdout: true` and leave the ones the synth learns from unmarked")
    if cfg.kind == "question":
        question.read(cfg)
    return replace(cfg, corpus=learned), replace(cfg, corpus=held)


def optimize(cfg, run_dir):
    learned, held = _split(cfg)
    model = cfg.models[-1]  # the weak leg is the optimization target — only misses teach
    log(f"baseline on weak leg [{model}], held-out entries first")
    scored = engine.bench(held, run_dir / "baseline-holdout", [model])[model]
    base_score = engine.objective_of(scored, cfg.objective)
    baseline = engine.bench(learned, run_dir / "baseline", [model])[model]

    log("synthesizing an improved subject from the misses")
    candidate = _synth(cfg, run_dir, model, baseline)
    imp_score, kept = _try_candidate(held, run_dir, model, candidate, base_score)
    verdict = "KEPT" if kept else "REVERTED"
    log(f"{cfg.objective} on held-out: baseline={base_score:.3f} improved={imp_score:.3f} -> {verdict}")
    (run_dir / "result.json").write_text(json.dumps(
        {"objective": cfg.objective, "baseline": base_score, "improved": imp_score,
         "kept": kept, "held_out": [task.name for task in held.corpus]}, indent=2))
    return kept
