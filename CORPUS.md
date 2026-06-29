# Authoring a corpus

A task in proofbench is a git repository with two branches: a `default_branch` in a broken or
incomplete state, and an `answer_branch` holding the ground-truth change. The judge grades the
agent's diff against `default_branch..answer_branch`. The quality of your eval is mostly the
quality of these tasks. Two rules carry the most weight.

## Do not use famous bugs

A capable model recognizes Heartbleed, Shellshock, or a textbook off-by-one on sight. When it
does, you are measuring what it memorized, not how it debugs. Prefer subtle, real defects where
the correct reasoning is about an invariant, a race, or a contract, and where the surrounding
code gives no hint. The discriminating tasks are the ones a model has to actually reason through,
not pattern-match.

## Do not telegraph the answer

The judge reads the repo's README. If the README says "this repo has an intentional bug for
practice," or the buggy line carries a `# Buggy` comment, the judge (and the agent) read the tell
instead of the contract. In one real run this flipped genuine contract violations into "intended
design" and quietly corrupted the grades. So:

- Write the README as a real library would: state what each function is supposed to do (its
  contract), never that it is wrong.
- Remove comments that point at the defect. Keep the buggy line exactly where it is.
- The only place the answer should exist is the `answer_branch`.

## Practical shape

- One defect (or one coherent set) per task keeps recall and precision interpretable.
- Keep `default_branch` checked out as the repo's default, so a fresh clone is in the broken
  state the agent will see.
- The bundled `examples/sample-corpus/build.sh` is a minimal worked example: two repos, each a
  `buggy` branch and a `fixed` branch, README stating the contract, no tells.

## Pointing the harness at your corpus

Each task in the config names the repo path and its two branches:

```yaml
corpus:
  - name: my-task
    path: /abs/or/relative/path/to/repo
    invoke: "Find and fix the bug in this repository."
    default_branch: buggy
    answer_branch: fixed
```

Large or licensed corpora should not be committed into your harness repo. Reference them by a
pinned git URL and clone them on setup, so the data stays out of your tree and its provenance
stays exact.
