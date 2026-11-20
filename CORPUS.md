# Building a repo corpus

How to build repo tasks that separate a good agent from a weak one and do not give their
answers away. For question tasks, see [docs/question-tasks.md](docs/question-tasks.md).

[Back to the README](README.md)

## Contents

- [What a task is](#what-a-task-is)
- [How a task is scored](#how-a-task-is-scored)
- [Two ways a task leaks its answer](#two-ways-a-task-leaks-its-answer)
- [A checklist for each task](#a-checklist-for-each-task)
- [Wiring a task into the config](#wiring-a-task-into-the-config)
- [Tasks from other people's repositories](#tasks-from-other-peoples-repositories)

## What a task is

A task is a git repository with two branches.

- **The default branch** holds the broken or unfinished state. The agent starts here.
- **The answer branch** holds the fix. The agent never sees it.
- **The reference solution** is the diff between the two. The judge grades against it.

```mermaid
flowchart LR
  subgraph repo["task: one git repository"]
    A["default_branch<br/>(e.g. main / buggy)"]
    B["answer_branch<br/>(e.g. solution / fixed)"]
  end
  A -- "reference solution<br/>git diff default_branch..answer_branch" --> B
```

Branch names vary from repo to repo: `main`, `master`, `buggy`, `solution`, `working`. The
config's `default_branch` and `answer_branch` fields say which is which.

A good task has two properties:

- **It discriminates.** A capable agent solves it and a weak one does not.
- **It does not leak.** Nothing but the answer branch reveals the fix.

## How a task is scored

```mermaid
flowchart TD
  clone["fresh clone of default_branch"] --> run["runner starts the agent"]
  run --> cap["capture: git diff of the clone<br/>= the agent's patch"]
  gt["ground truth:<br/>default_branch..answer_branch"] --> judge
  cap --> judge{{"judge"}}
  judge --> out["recall · precision"]
```

- **The agent works in a throwaway clone.** It holds the default branch alone and has no
  remote, so the answer cannot be fetched. Your corpus repo is only read.
- **Recall** is how much of the reference solution the agent reproduced.
- **Precision** is how much of the agent's patch was needed, not collateral damage.
- **An agent that changes nothing** is graded on its empty diff and counted in the average.

One clear defect per task keeps both numbers easy to read.

## Two ways a task leaks its answer

A task leaks when the agent or the judge can reach the answer without doing the work.

```mermaid
flowchart TD
  task["answer leakage"]
  task --> c["Contamination<br/>the model already memorised the fix"]
  task --> l["Label leakage<br/>the repo points at the fix"]
  c --> cc["famous CVEs · textbook off-by-ones<br/>→ measures memory, not method"]
  l --> ll["'intentional bug' READMEs · '# Buggy' comments<br/>→ judge grades the tell, not the contract"]
```

### Contamination: avoid famous defects

- A capable model recognises Heartbleed, Shellshock or a textbook off-by-one on sight.
- When it does, you are measuring what it remembers, not how it debugs.
- Prefer subtle, real defects whose fix turns on an invariant, a race or a contract.
- Prefer fixes newer than the model's training data.

### Label leakage: do not point at the answer

The judge reads the repo's README. If the README says "this repo has an intentional bug", or
the broken line carries a `# Buggy` comment, both the agent and the judge read the hint
instead of the code. In one real run this turned real contract violations into "intended
design" and quietly corrupted the grades.

- Write the README as a real library would. State what each function is supposed to do, never
  that it is wrong.
- Remove comments that point at the defect. Leave the broken line where it is.
- Keep the fix in exactly one place: the answer branch.

## A checklist for each task

- [ ] The repository root is the task. A folder inside another repository is refused.
- [ ] The default branch is a branch or tag, and it holds the broken state.
- [ ] The answer branch differs from the default branch.
- [ ] Every file the answer branch changes is part of the fix, or is listed under `ignore`.
- [ ] If the answer changes more than the fix inside a file, the task lists its `items`.
- [ ] The README states the contract and does not mention the bug.
- [ ] No comment points at the defect.
- [ ] The defect is not famous.
- [ ] The task has one defect, or one coherent set.

`examples/sample-corpus/build.sh` is a small worked example: two repos, each with a `buggy`
branch, a `fixed` branch, and a README that states the contract.

## Wiring a task into the config

```yaml
corpus:
  - name: my-task                 # unique
    path: repos/my-task           # relative to the config file
    invoke: "Find and fix the bug in this repository."
    default_branch: buggy
    answer_branch: fixed
    holdout: true                 # optional; scored by optimize, never shown to the rewrite
    ignore: ["dist/**"]           # optional; paths that are not part of the fix
```

- Every field is described in [docs/configuration.md](docs/configuration.md#a-repo-task).
- `holdout` is explained in [docs/optimize.md](docs/optimize.md#the-held-out-split).

**Check what your answer branch really changes.** Run `git diff --stat default..answer` on
each task. Answer branches often carry more than the fix:

- a rebuilt bundle or other generated output
- a rewritten README
- a file of solution notes

The judge counts every change in the answer as something the agent should have done. On one
real task this scored an agent that fixed both bugs at 0.40 recall, because three of the five
"items" were files like these. List them under `ignore` and they are left out of both sides.

**Then check what it changes inside the files it fixes.** A real fix commit often rewords
docstrings or tidies nearby code in the same file, and `ignore` cannot leave that out. On one
real task, five of the judge's seven items were reworded docstrings, and an agent that fixed
one of the two real problems scored 0.14 where 0.50 was the honest number.

List the task's `items` and that stops:

```yaml
    items:
      - "a waiter that was notified and then cancelled passes the wakeup on to another waiter"
      - "the wakeup is also passed on when the cancel arrives while re-acquiring the lock"
```

- The judge rules on each item you wrote and cannot add its own.
- proofbench counts recall over your list.
- Write outcomes, not edits, so a different fix that works still counts.

## Tasks from other people's repositories

- Do not commit large or licensed corpora into your own repo.
- List them by URL and clone them at setup.
- **Pin both branches to exact commits.** If upstream moves its answer branch, an unpinned
  corpus quietly changes what you grade against.

`corpora/manifest.yaml` and `corpora/fetch.sh` show the pattern: each entry has a `pin` for
the default branch and an `answer_pin` for the answer branch.

**A real fix makes a good task.** Take a merged bug fix from a real project:

- The commit just before the fix is the broken state.
- The fix commit is the answer.
- If the project is large, cut the task down to the files the fix changed.

`corpora/build_hard.py` builds three tasks this way, from the `upstream` entries in the
manifest. Each names a project, one file, the fix commit and its parent.

**An existing benchmark makes a good check.** `corpora/build_swebench.py` builds SWE-bench
Verified instances from the `swebench` entries in the manifest:

- One repo per upstream project, with two branches per instance. `<name>` is the base
  commit and `<name>-fixed` adds the gold patch.
- The issue text is committed as `README`, so it is the task description the judge is shown.
- Each entry pins the base commit and the hash of the gold patch. Run the script with
  `--pin NAME` to print an entry to paste.
- These instances are not in `corpora/proofbench.yaml`. They exist to compare proofbench's
  grades with patches that each project's own tests have already passed or failed.
