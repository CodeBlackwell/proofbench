# Building an eval

An eval is worth running only after it has been checked. This page covers the four gates an
eval passes, the controls one of them grades, and the commands that decide each gate.

[Back to the README](../README.md)

## Contents

- [The idea](#the-idea)
- [The commands](#the-commands)
- [The gates](#the-gates)
- [Controls](#controls)
- [The command grader](#the-command-grader)
- [Grading the path](#grading-the-path)
- [The state file](#the-state-file)
- [Running an unchecked eval](#running-an-unchecked-eval)

## The idea

- A score from a broken eval looks exactly like a score from a working one.
- So `run` and `optimize` refuse an eval until four gates have passed on it as it stands.
- Every gate is decided by a command and its exit code. Nobody rules by eye that an eval is
  sound.
- The `/proofbench` skill walks you through all of it. This page is what the skill runs.

## The commands

| Command | What it does | Costs money |
|---|---|---|
| `proofbench status --config FILE` | Print each gate: passed, failed, stale or not run | No |
| `proofbench controls --config FILE` | Write the mechanical controls and their predictions | No |
| `proofbench check GATE --config FILE` | Run one gate and record the result | Depends on the gate |

- `status` exits 0 only when every gate has passed.
- `check` exits 0 when the gate passed and 1 when it failed.
- Run them from the eval folder, so `runs/` lands beside the config.

## The gates

Work through them in this order.

| Gate | Passes when | What it runs |
|---|---|---|
| `adapter` | The runner starts your system on the first task and a result comes back | One attempt on the last model in `models` |
| `coverage` | Every class in `classes` has a task, and every task is in a declared class | Nothing |
| `controls` | Every control is scored inside its predicted range | The grader, on each control |
| `headroom` | The first model in `models` scores below 1 on the whole eval | One full leg |

**`adapter`**

- A question corpus passes when the arm returns a valid result object.
- A repo corpus passes when the agent leaves a diff.
- When the eval grades the path, the adapter must leave a step log as well. See
  [Grading the path](#grading-the-path).

**`coverage`**

- List the kinds of answer your eval must cover under `classes` in the config.
- Label each question with a `class` field, or each repo task with a `class` key.
- An eval with no `classes` fails this gate. A score over an eval that never asks for one
  kind of answer cannot catch a system that always, or never, gives it.

**`headroom`**

- If the strongest model scores everything, the eval can show that a change made things
  worse and never that one made them better.
- A question corpus is read on `accuracy`. A repo corpus is read on its `objective`.

## Controls

A control is a result whose right score you know before the grader sees it.

**What `proofbench controls` writes**

It writes into a `controls` folder beside the config. For each question:

| Control | What it is | Must be graded |
|---|---|---|
| `answer` | The expected ids | Correct |
| `named` | The answer in words, with no ids, so the judge has to read it | Correct |
| `nothing` | An abstention | Correct only if the question is unanswerable |
| `noise` | The answer to a different question | Wrong |
| `half` | Half the expected ids, when there are two or more | Wrong |

For each repo task the judge grades:

| Control | What it is | Predicted recall |
|---|---|---|
| `answer` | The answer diff | 1 |
| `nothing` | An empty diff | 0 |
| `noise` | A new file unrelated to the task | 0 |
| `half` | The first half of the answer's hunks | Above 0 and below 1 |

- `half` is left out when the task lists `items`, or when the answer has one hunk.
- A repo task graded by command gets no files. Its starting state must fail and its answer
  must pass.

**The predictions**

- `controls/predictions.json` holds a range for every control, such as
  `{"primes/half": {"recall": [0.01, 0.99]}}`.
- It is written before anything is graded, so a prediction cannot be fitted to a grade.
- A control with no prediction, or a prediction with no control, fails the gate.

**Controls you add by hand**

- The mechanical controls cannot test everything. A fix that breaks something else, or an
  answer that is right for the wrong reason, has to be written by a person.
- Add the file beside the others: `controls/TASK/NAME.patch` for a repo task, or
  `controls/QUESTION_ID/NAME.json` holding an arm result for a question.
- Add its range to `predictions.json` before you grade it.
- Running `proofbench controls` again rewrites the mechanical controls and keeps yours.

**When a control misses**

- The grader is wrong, or the prediction was. Find out which before changing either.
- Fix the rubric when the grader is wrong. Changing the prediction to match the grade
  removes the check.

## The command grader

Where something can be run, grade with it. It is free and gives the same answer every time.

```yaml
corpus:
  - name: primes
    path: repos/primes
    invoke: "Find and fix the bug."
    default_branch: buggy
    answer_branch: fixed
    check: "python -m pytest -q tests/test_primes.py"
    hidden: [tests/test_primes.py]
```

- `check` is a shell command run in the agent's clone after it has finished. Exit 0 is a
  pass.
- `hidden` lists paths that exist on the answer branch. They are copied into the clone just
  before `check` runs, over anything the agent left there.
- Keep the hidden paths off the starting branch, so the agent can neither read nor edit them.
- The task's grade is `passed`, 1 or 0, and the leg's score is `macro_passed`.
- No judge is asked, so a corpus graded only by command needs no `judge` key.
- A corpus uses one grader. Tasks with `check` and tasks without cannot share a config.

## Grading the path

An outcome grade says whether the result was right. A path grade says how the system got
there: which tools it called, in what order, and what came back. It is optional, and it never
changes the outcome grade.

**The step log**

- Your adapter writes one line per tool call to the file named in the `PROOFBENCH_STEPS`
  environment variable: `{"tool": "search", "input": {}, "result": "..."}`.
- The built-in `claude` runner needs no adapter. Its steps are read from the CLI's stream.
- The format is in [io-contracts.md](io-contracts.md#the-step-log).

**The config**

```yaml
path:
  rules:
    - called: list_findings                   # called at least once
    - never_called: delete_capture            # never called
    - before: [list_findings, get_detection]  # no get_detection without a list_findings ahead of it
    - max_steps: 8                            # at most this many steps
    - script: rules/grounded.py               # whatever the four above cannot say
  judge: path-judge.md                        # a rubric a judge reads the path against
```

- Give `rules`, `judge`, or both. The rules apply to every task.
- A script is run as `SCRIPT STEPS_FILE ANSWER_FILE`. Exit 0 means the rule held and exit 1
  means it did not. Its first line of output is kept as the reason. Any other exit code
  stops the run, because a rule that crashed has not failed anyone.
- The path judge is shown the task, the step log and the recorded good path. It is never
  shown the system's answer. A check that ties the answer to the path belongs in a script.
- The path judge replies with `{"sound": 1, "why": "..."}`, or `0`. It is asked by
  `judge_model`.

**What a run reports**

| Question corpus | Repo corpus | Meaning |
|---|---|---|
| `rules_held_rate` | `macro_rules_held` | Share of attempts where every rule held |
| `path_sound_rate` | `macro_path_sound` | Share of attempts the path judge called sound |

**Recorded good paths**

- Keep one real path per task that you accept as good, in `paths/TASK/`.
- Copy two files there from that task's folder in a run: `steps.jsonl`, and the answer file
  (`answer.json` for a question, `agent.diff` for a repo task).
- The path judge is shown the recorded steps as an example. A path is not scored by how
  closely it matches.
- A recorded path must itself pass every rule. The `good` control checks that.

**Path controls**

`proofbench controls` builds these from each recorded path:

| Control | What it is | Must be graded |
|---|---|---|
| `good` | The recorded path as it was | Every rule held, and sound |
| `empty` | No steps | Not sound. Rules not held, when there is a `called` rule |
| `removed` | The path without the tool your first `called` rule names | Rules not held, and not sound |
| `reordered` | The path with the first tool of your first `before` rule moved to the end | Rules not held, and not sound |

- `removed` and `reordered` are built only when the config has that rule and the recorded
  path calls those tools. Every prediction follows from a rule you declared.
- Each control is a folder, `controls/TASK/NAME.path/`, holding a `steps.jsonl` and the
  answer file.
- A control for a script rule or for the rubric is written by hand, in the same shape, with
  a line in `predictions.json` such as `{"TASK/invented-number.path": {"rules_held": [0, 0]}}`.
- An eval with a `path` key and no path control fails the `controls` gate.

**The order, with a path**

- Recorded paths come from a run, so check `headroom` before `controls`. Its run folder
  holds a step log and an answer file for every task.
- A change under the `path` key turns `controls` stale and leaves the other three passed.
  Adding or removing the key itself turns `adapter` stale too.

## The state file

- `gates.json` sits beside the config. Only `proofbench check` writes it.
- Each gate's record holds whether it passed, the date, what it cost, and a hash of what it
  covered.

| Gate | Its hash covers |
|---|---|
| `adapter` | The config without its `path` key, whether there is one, and the runner file |
| `coverage` | The config without its `path` key, and the tasks |
| `controls` | The config, the tasks, the judge prompt and the `controls` folder. With a path: the rubric, the rule scripts and the `paths` folder too |
| `headroom` | The config without its `path` key, the runner file, the tasks and the judge prompt |

- When any covered file changes, the gate reads as **stale**, and a stale gate does not count
  as passed.
- The config is covered as it parses. Rewording a comment or reordering its keys leaves
  every gate as it was.
- For a repo corpus, "the tasks" means the commits both branches point at.
- The system you are evaluating is covered by no gate, so changing it never makes the eval
  stale.
- Commit `gates.json` and the `controls` folder with the eval. They are the proof that it
  works.

## Running an unchecked eval

```bash
proofbench run --config FILE --unchecked
```

- `--unchecked` runs an eval whose gates are open. It works on `optimize` too.
- Every scoreboard records which it was: `eval_checked` is `true` only when every gate had
  passed.
- The demos in this repository are stubs with no gates, so they need the flag.
