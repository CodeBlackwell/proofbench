# Inputs, outputs and contracts

What proofbench hands to each program it starts, what it expects back, and what it writes to
disk. Read this to write your own runner or arm, or to read a run's files.

[Back to the README](../README.md)

## Contents

- [The big picture](#the-big-picture)
- [The repo runner](#the-repo-runner)
- [The question arm](#the-question-arm)
- [The step log](#the-step-log)
- [The judge and the synth](#the-judge-and-the-synth)
- [The run folder](#the-run-folder)
- [The repo scoreboard](#the-repo-scoreboard)
- [The question scoreboard](#the-question-scoreboard)
- [Files optimize adds](#files-optimize-adds)
- [Exit codes and logs](#exit-codes-and-logs)

## The big picture

```
config.yaml ──► proofbench run | optimize ──► runs/<run-id>/
                      │
      ┌───────────────┼────────────────┐
      ▼               ▼                ▼
   agent / arm      judge            synth
  (does the task) (grades it)   (rewrites the subject,
                                  optimize only)
```

proofbench starts three kinds of program. Each has a small, fixed contract.

## The repo runner

The runner does a repo task. It is started once per task per model.

**How it is started**

- Built in: `claude -p <invoke> --model <model> --dangerously-skip-permissions
  --output-format json --max-turns <max_turns>`
- Your own: `<runner> <invoke> <model>`. Give a file, relative to the config, or a command
  on your PATH.

**What it gets**

- Its working directory is a fresh clone of the task's `default_branch`, in the system temp
  folder.
- The clone holds that one branch and has no remote. The answer branch is not in it.

**What it must do**

- Change the files in that directory. It may commit or not; both are captured.
- Its exit code and its printed output are not trusted. Only the diff counts.
- Its cost is read from its output when it prints the result object the `claude` CLI prints:
  the one line of `--output-format json`, or the `result` event of a stream. A runner that
  starts `claude` only has to print what `claude` printed. With no such object the cost is
  recorded as unknown.

**What is captured**

- A `git diff` of the directory against the starting commit, including new files.
- Left out of the diff, because they are never the fix:
  - `node_modules`, `.venv` and `__pycache__`, at any depth.
- Also left out: any path the task lists under [`ignore`](configuration.md#a-repo-task).
- Nothing else is left out. If a tool your agent runs leaves its own files in the repo, such
  as an `AGENTS.md` or a cache folder, list them under `ignore` or they are graded as changes.
- New files are found under the ignore rules the repo had **before** the agent ran. A
  `.gitignore` the agent writes, edits or deletes changes nothing about what is captured, and
  its change to that file is itself in the diff.
- Git's other ways of hiding work are switched off for the capture: the clone's private
  exclude file, an excludes file named in git config, and the `assume-unchanged` and
  `skip-worktree` index flags.
- Your own global gitignore is not applied either, so the same agent output gives the same
  diff on every machine.
- With the `claude` runner, cost, turns and token counts are read from its output.

An agent that changes nothing leaves an empty diff. That diff is still graded and counted.

To grade a diff you already have, use `corpora/replay.sh` as the runner and put the patch's
full path in `invoke`. It applies the patch where an agent would have worked, so the same
diff can be graded as often as needed and no agent is paid for.

## The question arm

An arm answers one question. It is started once per question, per trial, per model.

**How it is started**

```
<runner> --model <model> <runner_args...>
```

**What it gets on stdin**

```json
{"id": "LQ-0001", "text": "Who supervised the doctoral advisor of Josephine Sundqvist?"}
```

Only `id` and `text`. The answer key never leaves the harness.

**What it must print on stdout**

One JSON object and nothing else:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `answer_ids` | list | yes | The ids the arm answers with |
| `abstained` | true or false | yes | True when the arm declines to answer |
| `tokens_in` | number | yes | Input tokens the arm spent |
| `tokens_out` | number | yes | Output tokens the arm spent |
| `answer` | text | no | The answer in words; the judge reads it when ids do not match |
| `cost_usd` | number | no | What the call cost |
| `seconds` | number | no | How long it took |
| `stubbed` | true or false | no | True when a canned reply answered, not a model |
| `model` | text | no | The model id that actually answered |

- A missing or wrongly typed required field stops the run. `"false"` in quotes is not false.
- A non-zero exit code stops the run. An arm leaves nothing else to grade.
- Anything the arm prints to stderr goes to its `run.log`.
- Report `stubbed` and `cost_usd` honestly. A leg counts as a measurement only when the arm
  says it was not canned and says what it cost.

## The step log

Written only when the config has a [`path`](building-an-eval.md#grading-the-path) key.

- **Where:** the file named by the `PROOFBENCH_STEPS` environment variable. proofbench sets
  it for a question arm and for an executable repo runner.
- **Format:** JSON lines, one step per line, in the order the steps were taken.

```json
{"tool": "list_findings", "input": {"upload_id": 1}, "result": "3 findings, worst first"}
```

| Field | Meaning |
|---|---|
| `tool` | The name of the tool that was called. Text |
| `input` | What it was called with. Any JSON value |
| `result` | What came back. Any JSON value, and null when no result arrived |

- All three fields are required on every line. A line without them stops the run.
- A system that called no tool still writes the file, empty. A missing file stops the run.
- The built-in `claude` runner is not given the variable. proofbench starts it with
  `--output-format stream-json --verbose` and reads the steps from that stream. Each
  `tool_use` block is a step, and the `tool_result` block carrying its id is the result. A
  subagent's calls are included, in the order they arrived.
- A repo runner is given a file outside the run folder, because the run folder holds the
  answer diff. The log is copied into the run folder afterwards.

**A rule script** is called as `SCRIPT STEPS_FILE ANSWER_FILE`.

- `STEPS_FILE` is the step log.
- `ANSWER_FILE` is what the system returned: the arm's result object as JSON for a question,
  or the agent's diff for a repo task.
- Exit 0 means the rule held and exit 1 means it did not. Any other code stops the run.
- The first line it prints is kept as the reason.

## The judge and the synth

Both are one call to `claude` with no tools and none of your personal configuration:

```
claude -p --model <model> --tools "" --safe-mode --output-format json
```

The whole prompt goes in on stdin. The reply must hold one JSON object.

| Call | What is sent | What must come back |
|---|---|---|
| Judge, repo task | Your judge prompt, the repo's README (any case, such as `readme.md`), the answer diff, the agent's diff | Any JSON object with at least one number, such as `recall` and `precision` |
| Judge, question | Your judge prompt, the question, the expected answer, the arm's answer and ids | `{"correct": 1}` or `{"correct": 0}`, with an optional `why` |
| Synth | Your synth prompt, the grades, the current subject | `{"subject": "...", "changelog": "..."}` |

- A reply with no usable object is asked for once more. A second failure stops the run.
- When a repo task lists [`items`](configuration.md#a-repo-task), the prompt also carries a
  `GROUND_TRUTH_ITEMS` section naming them `i1`, `i2` and so on. The reply must then hold
  `"items": [{"id": "i1", "fixed_by_agent": true}, ...]`, one entry per id. proofbench counts
  `recall` from those verdicts and overwrites whatever recall the judge wrote.
- A call that runs past 15 minutes stops the run.
- `NaN` is refused as a grade.
- On a question, the judge is only called when an exact id match and the abstention rule
  cannot settle the grade. See [how a question is graded](question-tasks.md#how-a-question-is-graded).

## The run folder

A repo corpus:

```
runs/<run-id>/
  scoreboard.json                      every model
  _ground-truth/<task>/answer.diff     the known answer
  <model>/
    scoreboard.json                    this model
    <task>/
      run.log                          what the agent printed
      agent.diff                       what the agent changed
      steps.jsonl                      the step log, when the path is graded
      grade.json                       the judge's reply, plus cost and timing for both
```

A question corpus:

```
runs/<run-id>/
  scoreboard.json                      every model
  <model>/
    scoreboard.json                    this model
    <question id>/trial-<n>/
      run.log                          what the arm printed
      result.json                      the arm's reply and its grade
      steps.jsonl                      the step log, when the path is graded
      answer.json                      the arm's reply alone, as a rule script is handed it
```

- The folder is created where you ran the command.
- Without `--run-id` it is named for the start time, such as `runs/20261120-064218`.
- A folder that already holds a run is refused.

## The repo scoreboard

```json
{
  "haiku": {
    "tasks": {
      "primes": {"recall": 1.0, "precision": 1.0},
      "ranges": {"recall": 0.5, "precision": 1.0}
    },
    "macro_recall": 0.75,
    "macro_precision": 1.0,
    "empty_captures": ["ranges"],
    "resources": {"seconds": 35.4, "cost_usd": 0.0168, "turns": 14, "judge_cost_usd": 0.0912},
    "eval_checked": true
  }
}
```

- `eval_checked`: true when every [gate](building-an-eval.md) had passed on this eval as it
  stood. False means the run was made with `--unchecked`. A question scoreboard carries the
  same key.
- `tasks`: the numbers the grader returned for each task. A task graded by command has
  `passed`, 1 or 0, and the leg has `macro_passed`. For a task that lists `items`,
  `recall` is counted by proofbench from the judge's verdict on each one.
- `macro_<field>`: the plain average of that field over every task. A field is averaged only
  if every task has it.
- `empty_captures`: tasks where the agent changed nothing. They are graded and averaged like
  any other. The key is absent when there are none.
- `resources`: seconds, cost and turns added up across the tasks. Cost and turns are null
  unless the runner reported them.
- `judge_cost_usd`, inside `resources`: what the judge cost across the tasks, kept apart from
  the agents' `cost_usd`. A reply the judge had to be asked for twice counts both times. The
  path judge's cost is added in here.
- `rules_held` and `path_sound`, 1 or 0 on each task, with `macro_rules_held` and
  `macro_path_sound` on the leg: present when the [path is graded](building-an-eval.md#grading-the-path).
  Each task's `grade.json` also holds `rules`, which names every rule, whether it held and
  why, and `path_why`, the path judge's reason.

## The question scoreboard

Each model's entry has three parts.

**Where the numbers came from**

| Key | Meaning |
|---|---|
| `stubbed` | True if any reply was canned, false if the arm said none were, null if it never said |
| `model` | The model id the arm reported |
| `cost_usd` | Total reported cost, or null if none was reported |
| `is_measured` | True only when the arm said it was not canned and reported a cost above zero |
| `not_measured_why` | The reasons, when `is_measured` is false |

**The numbers**

| Key | Meaning |
|---|---|
| `questions`, `trials` | How many questions, and how many times each was asked |
| `answerable`, `unanswerable` | How many questions of each sort |
| `measures` | `accuracy and abstention`, or `abstention only` |
| `accuracy`, `correct`, `tokens_per_correct` | Present when at least one question was answerable |
| `abstention_rate`, `correct_abstentions`, `tokens_per_correct_abstention` | Present instead when none was |
| `pass^k`, `pass@k` | One pair for every k up to `trials` |
| `unstable_questions` | Ids answered both right and wrong across trials |
| `non_abstention_rate_answerable` | Share of answerable attempts where the arm did answer |
| `abstention_correct_unanswerable` | Share of unanswerable attempts where the arm declined |
| `tokens_in`, `tokens_out`, `tokens_total` | Token totals over every attempt |
| `rules_held_rate`, `path_sound_rate` | Present when the [path is graded](building-an-eval.md#grading-the-path): the share of attempts where every rule held, and the share the path judge called sound |

What each number means is in [question-tasks.md](question-tasks.md#the-numbers).

**The records**

`records` holds one entry per attempt: the question, the trial number, the arm's answer,
whether it was correct, and what decided the grade (`abstention`, `exact` or `judge`). Any
grouping can be rebuilt from them without running the arm again. When the path is graded, a
record also holds `rules` (every rule, whether it held and why), `rules_held`, `path_sound`,
`path_why` and `path_judge_cost_usd`.

## Files optimize adds

```
runs/<run-id>/
  baseline-holdout/    the held-out entries, before the rewrite
  baseline/            the entries the rewrite learns from
  improved/            the held-out entries, after the rewrite
  subject.bak          the subject as it was
  subject.candidate    the rewrite
  changelog.md         what the synth says it changed
  result.json          the verdict
```

`result.json`:

```json
{"objective": "macro_recall", "baseline": 0.5, "improved": 0.75, "kept": true, "held_out": ["check-1"]}
```

Outside the run folder, `optimize` writes one thing: your `subject` file, and only when the
rewrite is kept.

## Exit codes and logs

- Progress is printed to stderr, each line starting with `[proofbench]`.
- Exit code 0 means the run finished. It does not mean the agent did well.
- Exit code 1 means a hard stop. The reason is the last line, in red.
