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
timeout_minutes: 60                             # optional; one attempt running longer stops the run
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

Each run writes to its own folder, `runs/<start time>/`, or `runs/<run-id>/` with `--run-id`. A
folder that already holds a run is refused, so one run's files are never read as another's.

The config is checked whole before anything is paid for. A key proofbench does not read, a
`models` that is not a list, a file that does not exist, or an objective the gate cannot
compare is a hard stop at load. `models` is ordered strongest first: `judge_model` and
`synth_model` default to the first entry, and `optimize` rewrites against the last.

### Two task kinds

A corpus entry's `kind` decides what is captured and how it is graded. One corpus holds one
kind.

- **`repo`** (the default, and everything above): the agent edits a repository, capture is a
  git diff against the broken branch, and the judge grades that diff against an answer branch.
- **`question`**: the agent answers a question with a known answer. The corpus is a JSONL
  file, one question per line; the runner is any executable that is handed a question's `id`
  and `text` on stdin, never its answer key, and prints one result object on stdout; nothing
  is cloned and no diff is taken.

```yaml
runner: arms/oracle-tier1.py          # any executable; no built-in runner drives a question
runner_args: [--snapshot, 3f9a2c1b]   # appended after --model MODEL; quote every number
models: [sonnet]                      # passed to the arm as --model
judge_model: opus
objective: tokens_per_correct
judge: judge.md                       # your own answer rubric; the question kind ships none
corpus:
  - kind: question
    file: questions/lineage.jsonl
```

`runner_args` is how an arm that must be told which frozen corpus to read, or which
configuration it is being measured under, is told: the flags live in the config, so the run is
reproducible from the config alone. A repo task is invoked `<runner> <invoke> <model>` and has
nowhere to put them, so carrying them there is a hard stop.

The arm prints `{answer, answer_ids, abstained, tokens_in, tokens_out, cost_usd, seconds,
chunks, path}`. `answer_ids` (a list), `abstained` (true or false) and the two token counts
(numbers) are required, and a missing or mistyped one is fatal; the rest are logged. An arm
may also report `stubbed` and `model`, which the scoreboard's provenance line reads.

Every question needs `id`, `text`, `answer`, `answerable`, `tier` and `hops`, with `tier` and
`hops` on the stratification grid. The question file is checked before any arm is asked, and
a line that fails is named by its number.
Grading is an exact match on `answer_ids` after normalisation first, and the judge only when
prose or a number written as words has to be read. An abstention is correct exactly when the
question's `answerable` is false.

The scoreboard reports how many of the questions were answerable, abstention split by both
answerabilities, total tokens, and every per question record, so any question field regroups
it. A leg that was asked an answerable question reports `accuracy` and `tokens_per_correct`. A
leg whose questions were all unanswerable reports `abstention_rate` and
`tokens_per_correct_abstention` and carries no key named accuracy at all: a corpus that can
only measure abstention has to produce a board that can only be read as abstention. `run`
prints the tier by hop depth grid over the fifteen cells the stratification fixes, the empty
ones included, under a heading naming the metric in it. A leg with nothing correct reports its
price as null, never zero, and reading it as an objective is a hard stop. Try it offline:

```bash
proofbench run --config examples/question-demo/proofbench.question.yaml
```

### Repeated trials: pass^k and pass@k

One trial of a question says whether the arm can be right. It does not say whether the arm is
right every time. `trials` asks every question that many times, each trial a fresh arm process:

```yaml
trials: 3
objective: pass^3        # any pass^k or pass@k up to the trials run can be the objective
```

- **`pass^k`**: the chance that k trials of one question are all correct. The reliability
  reading, and the one to gate on for anything a person will rely on unattended.
- **`pass@k`**: the chance that at least one of k trials is correct. The capability reading.

Both are averaged over the questions and reported for every k from 1 to `trials`, so one run
yields the whole curve. With c of n trials correct a question contributes `C(c,k)/C(n,k)` to
`pass^k` and `1 - C(n-c,k)/C(n,k)` to `pass@k`. `pass^1` and `pass@1` both equal `accuracy`,
which counts trials. The gap between `pass@k` and `pass^k` is the arm's inconsistency, and
`unstable_questions` names the questions behind it: those answered both right and wrong.

What changes with trials:

- Every record carries its `trial`, and each trial keeps its own `result.json` and `run.log`
  under `runs/<run-id>/<model>/<question id>/trial-<n>/`.
- `questions`, `answerable` and `unanswerable` count questions, never trials. Token and cost
  totals cover every trial.
- `run` prints the curve under the headline, and a second grid of `pass^k` at the full trial
  count beside the accuracy grid.
- A leg that measured only abstention carries the curve as `abstention_pass^k` and
  `abstention_pass@k`, for the same reason it carries no key named accuracy.

Hard stops: an objective naming a k above `trials` or one the gate has no direction for, two questions sharing an id, questions
asked unequal numbers of times, and `trials` on a repo corpus, which has no right or wrong
grade per attempt to count.

### The keep/revert gate

`optimize` runs a baseline on the weak leg, asks an LLM to rewrite the subject from the graded
misses, re-runs, and keeps the rewrite only if the objective did not regress. The decision is
the harness comparing two numbers, never the model's own claim of success.

The comparison runs in the objective's own direction: a higher rate, recall or `pass^k` is
kept, and so is a lower `tokens_per_correct`.

On a question corpus the rewrite is shown only the questions the weak leg got wrong on at least
one trial: the question, the expected answer, and what each trial answered. A baseline with
nothing wrong is a hard stop before the rewrite, since there is nothing to learn from. The
baseline and the re-run use the same questions, so a gain can be the subject fitting those
questions. Check a kept rewrite on a question file the loop never saw.

## Adapters

- **Runner** (`runner:`): `claude` is built in. Any other value is an executable invoked as
  `<runner> <invoke> <model>` for a repo task, or as `<runner> --model <model> <runner_args>`
  with the question on stdin for a question task, so you can drive aider, codex, or a custom
  agent.
- **Capture**: the git-diff default clones a repo's default branch into a throwaway directory,
  runs the agent there, and snapshots what it changed against the baseline commit, excluding
  dependency and cache trees so they never pollute or balloon the judge prompt. The corpus repo
  is only read, and the clone holds neither the answer branch nor a remote to fetch it from. An
  agent that changes nothing is graded on its empty diff and counted in the macro average. A
  question task captures the arm's result object instead.
- **Judge and synth**: both run `claude -p --tools "" --safe-mode`, so they have no tools and
  none of your CLAUDE.md, hooks, plugins or MCP servers. That needs a Claude Code version with
  both flags; an older one stops the run with the CLI's own error.

## Bring your own corpus

The bundled corpus is two MIT toy repos for the demo. Point `corpus:` at your own repos
(each with a broken default branch and a fixed solution branch). See [CORPUS.md](CORPUS.md) for
how to curate tasks that actually discriminate and do not leak their answers to the judge.

## License

MIT.
