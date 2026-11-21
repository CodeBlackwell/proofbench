---
name: proofbench
description: Build an eval for an agentic system and take it through the gates that prove it can be trusted. Use when the user wants to evaluate, benchmark or measure an agent, skill or LLM system of their own, asks to "build an eval", or wants to resume or check one. Writes the eval into the target system's repo; the proofbench CLI decides every gate.
argument-hint: "[path to the target repo or to an existing eval folder]"
user_invocable: true
---

# proofbench: build an eval you can trust

You are building an eval for a system the user owns. You write the files. The `proofbench`
CLI decides whether the eval is sound. You never decide that yourself.

## Rules that do not bend

- **An eval is finished only when `proofbench status` exits 0.** Never say an eval is done,
  ready or trustworthy on any other evidence.
- **Never write or edit `gates.json`.** Only `proofbench check` writes it.
- **Never change a prediction to match a grade.** When a control misses, find out whether the
  grader or the prediction is wrong, show the user the evidence, and let them decide.
- **Never accept an answer a model invented** without the user approving that one answer.
  Mine answers from history the user owns, or ask the user for them.
- **State the cost and wait for a yes before every paid step.** The paid steps are
  `check adapter`, `check controls` when a judge grades, and `check headroom`.
- **Never run `proofbench run` or `optimize` with `--unchecked` to get a score to report.**

## Step 0: find out where you are

1. Run `proofbench --version`. If it is missing, ask before installing it with
   `uv tool install proofbench`.
2. Find the eval folder. It is `evals/<name>/` in the target repo and holds `proofbench.yaml`.
3. If it exists, run `proofbench status --config proofbench.yaml` from inside it and resume at
   the first gate that is not `passed`. Skip to that gate's step below.
4. If it does not exist, start at step 1.
5. Look for `evals/docket.md`. It is written by `/eval-docket`, and records which claims the
   owner wants tested, where the answers come from, and what was ruled out.
   - **If it is there, read it first.** Take the classes, the answer source, the grader and
     the rulings from it, and do not ask again what it already answers. Build nothing it
     lists as not testable.
   - **If it is not, offer to run `/eval-docket` first,** in one line, and carry on with
     step 1 if the user declines.
   - **The docket guides and passes no gate.** When a gate and the docket disagree about a
     fact, the gate is right; tell the user, so the docket can be corrected.

Run every `proofbench` command from inside the eval folder, so `runs/` lands there.

## Step 1: learn the system

Read the target repo before asking anything. Find these yourself:

- How the system is started, and whether one command can run it headless.
- What it leaves behind: a diff in a repo, or an answer.
- Whether it has tests or another check a command could run.
- Where results with known right answers already exist: fixed bugs in git history, labelled
  fixtures, ground-truth files, resolved tickets, logs with a known verdict.

Then ask the user only what neither the repo nor a docket can tell you:

- What claim the eval should test. One sentence.
- What a right result looks like, and what the kinds of right and wrong result are. These
  become the answer classes.
- Whether how the system gets to its result matters, or only the result. If it matters, the
  eval grades the path too. See "The path" below.
- Which models to run, strongest first.
- How the system's model calls are paid for: its own API key, or the Claude subscription
  through the `claude` CLI. For the subscription, the adapter stands where the system
  expects its model client and asks `claude -p` instead. Say plainly what that changes
  about the wire, such as tool calls carried in a JSON reply.

## Step 2: choose the shape

| The system leaves | Task kind | Grader |
|---|---|---|
| A change to a repo, and a command can check it | repo | `check` command with `hidden` files |
| A change to a repo, and nothing can be run | repo | LLM judge, `judge: default` |
| An answer in words | question | Exact id match first, your `judge.md` for prose |
| An id from a fixed list, such as a label | question | Exact id match alone: leave `judge` out |

Prefer the command grader wherever something can be run. Formats are in the plugin's docs:
`docs/configuration.md`, `docs/io-contracts.md`, `docs/question-tasks.md` and
`docs/building-an-eval.md`. Read the ones you need before writing a file.

## Step 3: write the eval folder

```text
evals/<name>/
  proofbench.yaml     the config, with `classes` listed
  adapter.sh          starts the system headless (the runner, or the arm)
  tasks/              question files, when the kind is question
  harvest.py          collects the real cases, when answers are mined
  judge.md            the rubric, when a judge grades
  path-judge.md       the path rubric, when a judge reads the path
  rules/              scripts for path rules the fixed kinds cannot say
  paths/              the recorded good path of each task
  controls/           written by `proofbench controls`, then added to by hand
  gates.json          written by `proofbench check`; never by you
  .gitignore          holds one line: runs/
```

- **The adapter** must be executable and take no secrets on its command line. When the repo
  already has a script that starts the system headless, point `runner` at it and write no
  adapter.
- **A harvester** is a small script the user can re-run. Commit it, so the tasks can be
  rebuilt and extended. It must not call a model to produce an answer. When the repo already
  mines its cases, the harvester copies them into `tasks/` and labels each with its class.
- **Leave out tasks whose answers a model wrote,** unless the user approves each answer.
- **Every task carries a class** from the config's `classes` list.
- **Write answers as outcomes**, never as the exact text or edit expected.
- **A question file never holds the answer in the question text.** A repo task's README never
  names the bug.

## Step 4: the gates, in order

For each gate: run it, read the result, fix what it found, run it again.

```bash
proofbench check adapter --config proofbench.yaml
```

1. **`adapter`** (one agent run). Fails: read `runs/<id>/run.log` and fix the adapter.
2. **`coverage`** (free). Fails: a declared class has no task, or a task has no declared
   class. Add tasks; do not delete the class to pass.
3. **`controls`**. First run `proofbench controls --config proofbench.yaml`. Then draft the
   controls the command cannot build, each a result that looks right and is wrong, or looks
   wrong and is right:
   - a fix that solves the task and breaks something else
   - an answer that names the right thing for the wrong reason
   - an answer that is right and worded nothing like the expected one
   Show each to the user with the score you predict. Only after they approve it, write the
   file and add its range to `controls/predictions.json`. Then run `check controls`.
4. **`headroom`** (one pass over every task on the strongest model, whatever `trials` says).
   Fails when that model scores 1: the eval is too easy to show an improvement. Add harder
   tasks from real history; do not remove easy ones to move the number. Fails when it scores
   0 too: check that each answer can be reached from what the system is shown, and tell the
   user when it cannot.

When a gate fails, `gates.json` holds the reason under `detail`.

## The path, when it is graded

Skip this section when only the result matters.

1. **The adapter writes the step log** to the file named in `PROOFBENCH_STEPS`: one JSON line
   per tool call, holding `tool`, `input` and `result`. The built-in `claude` runner needs
   nothing.
2. **Ask the user what a good path is,** and write their answer as rules under `path:` in the
   config. Use `called`, `never_called`, `before` and `max_steps` where they fit, and a
   `script` for the rest. Add a `judge` rubric only for what no rule can check: with one,
   every attempt costs a judge call.
3. **Check `adapter`, `coverage` and `headroom`.** With a path, `headroom` comes before
   `controls`, because its run folder holds a step log and an answer file for every task.
4. **Record good paths.** From the headroom run, list the attempts whose answer was right and
   whose rules all held. Show the user the list, and copy only the ones they approve:
   `steps.jsonl` and the answer file into `paths/<task>/`.
5. **Build and draft the path controls.** `proofbench controls` builds the mechanical ones
   from the recorded paths. Draft by hand, for each script rule and for the rubric, one path
   it must catch and one it must let through. Show each to the user with its prediction, and
   write only the approved ones as `controls/<task>/<name>.path/`.
6. **Check `controls`.**

A change under `path:` turns `controls` stale and leaves the other three passed. Adding or
removing `path:` itself turns `adapter` stale too.

## Step 5: finish

1. Run `proofbench status --config proofbench.yaml`. It must exit 0.
2. Tell the user what each gate cost, what the headroom score was, and which controls were
   written by hand.
3. Offer to commit the eval folder, `gates.json` and `controls/` included. Commit only when
   asked. Never push.
4. The eval now runs with `proofbench run --config proofbench.yaml`.

Any later change to the config, the tasks, the rubric, the adapter or the controls makes the
gates that covered it stale. Run `status` and re-check those gates.
