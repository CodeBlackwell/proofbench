# Configuration

One YAML file describes a whole run. This page lists every key, its default, and what is
checked when the file is loaded.

[Back to the README](../README.md)

## Contents

- [The basics](#the-basics)
- [Every key](#every-key)
- [Corpus entries](#corpus-entries)
- [Models and their order](#models-and-their-order)
- [The objective](#the-objective)
- [Prompts](#prompts)
- [What is checked at load](#what-is-checked-at-load)
- [Complete examples](#complete-examples)

## The basics

- **Paths are relative to the config file**, not to where you run the command. `~` works.
- **What the config contains decides what you can do.**
  - A corpus, a runner and a judge prompt let you `run`.
  - Adding `subject`, `synth`, an `objective` and held-out corpus entries lets you `optimize`.
- **Nothing is spent until the whole file passes its checks.**
- **`run` and `optimize` refuse an eval that has not passed its gates.** See
  [building-an-eval.md](building-an-eval.md).

## Every key

| Key | Default | Applies to | Meaning |
|---|---|---|---|
| `corpus` | required | both | The tasks. See [Corpus entries](#corpus-entries) |
| `models` | required | both | A list of model names to run, strongest first |
| `judge` | required on a repo corpus unless every task has a `check`; optional on a question corpus | both | Path to the judge prompt, or `default` on a repo corpus. A question corpus with none is graded by [exact id alone](question-tasks.md#how-a-question-is-graded) |
| `runner` | `claude` | both | What does the task. See [Runners](io-contracts.md#the-repo-runner) |
| `judge_model` | first of `models` | both | The model that grades |
| `synth_model` | first of `models` | both | The model that rewrites the subject in `optimize` |
| `concurrency` | `3` | both | How many attempts run at once |
| `timeout_minutes` | none | both | The longest one attempt may run. Longer stops the run |
| `objective` | `macro_recall` on a repo corpus (`macro_passed` when graded by command), none on a question corpus | both | The number the `optimize` gate compares |
| `subject` | none | both | Path to the file `optimize` rewrites |
| `synth` | none | both | Path to the rewrite prompt, or `default` on a repo corpus |
| `max_turns` | `200` | repo, `claude` runner only | Passed to `claude` as `--max-turns` |
| `runner_args` | `[]` | question only | Extra flags given to the arm after `--model MODEL` |
| `trials` | `1` | question only | How many times each question is asked |
| `judge_input_limit_kb` | `200` | both | The largest prompt a judge may be sent. Over it, the run stops and names the task |
| `classes` | none | both | The kinds of answer the [coverage gate](building-an-eval.md#the-gates) counts |
| `path` | none | both | How the steps the system took are graded: `rules`, a `judge` rubric, or both. See [Grading the path](building-an-eval.md#grading-the-path) |

Notes:

- `runner_args` must be a list of strings, so quote every number.
- `runner_args` and `trials` above 1 are refused on a repo corpus.
- A judge or synth call is limited to 15 minutes and is asked once more if its reply holds no
  usable object. `timeout_minutes` does not change that.

## Corpus entries

`corpus` is a list. Every entry must be the same kind.

### A repo task

```yaml
corpus:
  - name: primes                      # unique; names the output folder
    path: repos/primes                # the root of a git repository
    invoke: "Find and fix the bug."   # what the agent is asked to do
    default_branch: buggy             # a branch or tag: the broken starting state
    answer_branch: fixed              # a branch, tag or commit: the known answer
    holdout: true                     # optional; see docs/optimize.md
    ignore: ["dist/**", notes.md]     # optional; paths that are not part of the fix
    items:                            # optional; what the fix does, when you want to say so
      - "is_prime returns False for a composite number"
    check: "python -m pytest -q"      # optional; grade by this command and ask no judge
    hidden: [tests/test_primes.py]    # optional; answer-side paths copied in before `check`
    class: off-by-one                 # optional; the label the coverage gate counts
```

- `path` must be the root of its own repository, not a folder inside another one.
- `default_branch` must be a branch or tag name, because the agent's clone is made from it.
- The two branches must differ, or there is no answer to grade against.

**`ignore`** lists paths to leave out of the grade.

- Use it when the answer branch changes files that are not the fix: a rebuilt bundle, a
  rewritten README, a file of answer notes.
- Without it, each of those counts as something the agent failed to do, and recall drops for
  work no agent should reproduce.
- The paths are left out of **both** the answer and the agent's diff, so neither side is
  graded on them.
- Patterns are relative to the repo root. `*` stays inside one folder; `**` crosses folders,
  so `dist/**` means everything under `dist`.

**`items`** lists what the fix does, one line each.

- Without it, the judge decides what the items are: it reads every distinct change in the
  answer as one. That is fine when the answer is nothing but the fix.
- Use it when the answer changes more than the fix **inside the file it fixes**: reworded
  docstrings, cosmetic rewrites. `ignore` cannot leave those out, because it works on whole
  files.
- With it, the judge only rules true or false on each line you wrote. It cannot add, split or
  drop items.
- Recall is then counted by proofbench: items ruled fixed, divided by items listed.
- Write each item as an outcome ("a trailing backslash is not treated as an escape"), not as
  an edit ("add `from[1] != 0`"). A different change that reaches the same outcome should count.
- A judge reply that does not rule on exactly your items stops the run.
- If the patterns leave nothing of the answer, the run stops.
- How to build good tasks: [CORPUS.md](../CORPUS.md).

**`check` and `hidden`** grade the task by running a command. See
[the command grader](building-an-eval.md#the-command-grader).

### A question file

```yaml
corpus:
  - kind: question
    file: questions/lineage.jsonl     # one question per line
    holdout: true                     # optional; see docs/optimize.md
```

- The file format is in [question-tasks.md](question-tasks.md#the-question-file).
- You can list several files. Question ids must be unique across all of them.

## Models and their order

List `models` **strongest first**.

- `judge_model` and `synth_model` default to the **first** entry.
- `optimize` rewrites against the **last** entry, the weakest.
- Name `judge_model` yourself when you run a single weak model, or it will grade itself.

For a question corpus, each name is passed to your arm as `--model NAME`. It can be any string
your arm understands.

## The objective

The objective is the one number `optimize` compares before and after a rewrite. `run` does not
use it.

| Corpus | Allowed values | Better when |
|---|---|---|
| repo | Any `macro_<field>`, where `<field>` is a number your judge returns, such as `macro_recall` | Higher |
| question | `accuracy`, `abstention_rate`, `abstention_correct_unanswerable`, `pass^k`, `pass@k` | Higher |
| question | `tokens_per_correct`, `tokens_per_correct_abstention` | Lower |

- `k` in `pass^k` and `pass@k` cannot be larger than `trials`.
- A leg that measured only abstention names its curve `abstention_pass^k` and
  `abstention_pass@k`.
- Any other name is refused, because the gate would not know which direction is better.

## Prompts

- `judge` and `synth` are paths to text files you write.
- On a **repo** corpus, either may be the word `default`. That uses the prompt proofbench
  ships: a judge that returns `recall` and `precision`, and a synth that makes small targeted
  edits.
- The shipped judge counts an item as fixed only when the change that addresses it leaves the
  code working. A fix that also breaks behaviour that worked before is ruled not fixed, and
  the judge says what broke. A separate, unrelated harmful change is a false positive: it
  lowers `precision` and leaves `recall` alone.
  The judge decides this from the two diffs alone, with nothing run, so it can be wrong
  either way: it can miss a breakage, and it can rule one that is not there.
- On a **question** corpus, `default` is refused. A rubric for answers has to know the subject
  it grades, so you write your own. See `examples/question-demo/judge.md` for the shape.

## What is checked at load

Each of these stops the run before any agent or judge is started:

- The file is not valid YAML, or is not a mapping of keys.
- A key proofbench does not read. This catches typos such as `judge_modle`.
- `models` is missing, empty, or not a list of names.
- `concurrency`, `max_turns` or `trials` is not a whole number of at least 1.
- `timeout_minutes` is not a number above 0.
- The `judge`, `synth` or `subject` file does not exist.
- The `objective` is not one the gate can compare, or names a `k` above `trials`.
- A corpus entry is missing a field or carries a key proofbench does not read, or the corpus
  mixes kinds.
- Two repo tasks share a name.
- A repo corpus mixes tasks that have a `check` with tasks that do not, or a task lists
  `hidden` paths and has no `check`.
- `judge_input_limit_kb` is not a number above 0, or `classes` is not a list of strings.
- `path` holds neither `rules` nor `judge`, a rule is not one of the five kinds or has a value
  it cannot use, a rule script is missing or not executable, or the path's `judge` file does
  not exist.
- On a question corpus: the runner file is missing or not executable, or a question file does
  not exist.

Checked a moment later, still before any agent runs:

- A branch does not exist, or the answer branch changes nothing.
- A question line is not JSON, or is missing a required field. The error names the line.
- Two questions share an id.

## Complete examples

A repo corpus that can run and optimize:

```yaml
runner: claude
models: [opus, haiku]
judge_model: opus
objective: macro_recall
judge: default
synth: default
subject: ~/.claude/skills/my-skill/SKILL.md
timeout_minutes: 60
corpus:
  - { name: learn-1, path: repos/a, invoke: "/my-skill", default_branch: buggy, answer_branch: fixed }
  - { name: learn-2, path: repos/b, invoke: "/my-skill", default_branch: buggy, answer_branch: fixed }
  - { name: check-1, path: repos/c, invoke: "/my-skill", default_branch: buggy, answer_branch: fixed, holdout: true }
```

A question corpus with repeated trials:

```yaml
runner: arms/my-arm.sh
runner_args: ["--snapshot", "3f9a2c1b"]
models: [sonnet]
judge_model: opus
judge: judge.md
trials: 3
objective: pass^3
corpus:
  - { kind: question, file: questions/train.jsonl }
  - { kind: question, file: questions/heldout.jsonl, holdout: true }
```

Working files you can copy:

- `examples/proofbench.demo.yaml`: the repo demo.
- `examples/question-demo/proofbench.question.yaml`: the offline question demo.
- `corpora/proofbench.yaml`: five real repo tasks.
