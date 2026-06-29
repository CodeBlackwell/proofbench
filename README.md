# proofbench

A config-driven eval harness that grades and self-improves headless agent skills against
ground-truth corpora. You plant tasks you already have the answers to, run an agent skill
across them, and grade what it changed against the known answer with an LLM judge. Then you
let the harness rewrite the skill from its own misses and keep the rewrite only if the score
holds.

It started as the harness behind [crg-debug](examples/crg-debug/), a graph-driven debugging
skill. The methodology generalizes to any skill whose output you can compare to a known answer.

## Why it exists

A skill is only as trustworthy as the proof that it works. Anyone can write a prompt that
sounds like a methodology. The honest way to know is to measure it against ground truth, on
the model weak enough to embarrass it. Two ideas carry the whole design, both learned the hard
way (see [METHODOLOGY.md](METHODOLOGY.md)):

1. **Fail loud or do not measure.** Every empty or non-numeric grade is a hard stop. An eval
   that fails open does not just miss data, it manufactures false confidence.
2. **The weak model is the signal, not the noise.** A self-improving loop learns only from
   misses. Frontier models on easy tasks miss nothing, so they teach nothing. The weak leg is
   the curriculum.

## Install

```bash
uv tool install proofbench      # or: uvx proofbench
```

Requires the `claude` CLI on PATH for the default runner and for the judge.

## Quickstart (demo)

```bash
git clone https://github.com/CodeBlackwell/proofbench && cd proofbench
bash examples/sample-corpus/build.sh        # builds two toy repos with buggy + fixed branches
uvx --from . proofbench run --demo          # eval an agent over them, graded vs the answers
```

## How it works

One YAML config declares everything domain-specific; the engine is generic. The mode is
implied by what the config contains:

- a corpus + runner + judge gives you a **bench** (`run`)
- adding a `subject` + `synth` unlocks the **self-improving loop** (`optimize`)

```yaml
subject: ~/.claude/skills/crg-debug/SKILL.md   # optional; omit for pure-eval mode
runner: claude                                  # default adapter; any executable works
models: [opus, sonnet, haiku]                   # the driver sweep; the weak leg is the signal
judge_model: opus                               # held constant; never let a model grade itself
objective: macro_recall                         # the metric the keep/revert gate reads
judge: prompts/judge.md
synth: prompts/synth.md                          # present => `optimize` is available
corpus:
  - name: primes
    path: examples/sample-corpus/repos/primes
    invoke: "Find and fix the bug in this repository."
    default_branch: buggy
    answer_branch: fixed
```

```bash
proofbench run      --config proofbench.yaml    # eval + scoreboard
proofbench optimize --config proofbench.yaml    # baseline -> synth -> re-run -> keep|revert
```

### The keep/revert gate

`optimize` runs a baseline on the weak leg, asks an LLM to rewrite the subject from the graded
misses, re-runs, and keeps the rewrite only if the objective did not regress. The decision is
the harness comparing two numbers, never the model's own claim of success.

## Adapters

- **Runner** (`runner:`): `claude` is built in. Any other value is an executable invoked as
  `<runner> <invoke> <model>`, so you can drive aider, codex, or a custom agent.
- **Capture**: the git-diff default resets a repo to its default branch and snapshots what the
  agent changed, excluding dependency and cache trees so they never pollute or balloon the
  judge prompt.

## Bring your own corpus

The bundled corpus is two MIT toy repos for the demo. Point `corpus:` at your own repos
(each with a broken default branch and a fixed solution branch). See [CORPUS.md](CORPUS.md) for
how to curate tasks that actually discriminate and do not leak their answers to the judge.

## License

MIT.
