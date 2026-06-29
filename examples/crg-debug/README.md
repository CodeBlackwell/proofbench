# Example: crg-debug

crg-debug is the skill proofbench was built to evaluate: a graph-driven debugging skill that
maps a codebase, fans out parallel discovery, verifies findings adversarially, then fixes in
TDD waves. It is the worked example for the whole methodology
([../../METHODOLOGY.md](../../METHODOLOGY.md), [../../docs/crg-eval-journey.md](../../docs/crg-eval-journey.md)).

It is an **example subject, not a dependency**. proofbench installs with no crg-debug or
code-review-graph packages. To reproduce this example you supply your own crg-debug skill and a
corpus of bug-fix repos.

## A config that drives crg-debug

```yaml
subject: ~/.claude/skills/crg-debug/SKILL.md   # the artifact `optimize` rewrites
runner: claude
models: [opus, sonnet, haiku]                   # haiku is the weak leg `optimize` targets
judge_model: opus
synth_model: opus
objective: macro_recall
judge: ../../prompts/judge.md
synth: ../../prompts/synth.md

corpus:
  # your bug-fix repos, each with a broken default branch and a fixed answer branch.
  # see ../../CORPUS.md for how to pick non-leaky, discriminating tasks.
  - name: my-bug-repo
    path: /path/to/my-bug-repo
    invoke: "/crg-debug"
    default_branch: buggy
    answer_branch: fixed
```

```bash
proofbench run      --config examples/crg-debug/proofbench.yaml   # measure across the sweep
proofbench optimize --config examples/crg-debug/proofbench.yaml   # improve SKILL.md from misses
```

The original evaluation that produced the lessons in METHODOLOGY.md ran exactly this shape over
five debugging-interview repos plus three Tier-1 hard cases (CPython timsort, asyncio Condition,
and the sudo Baron Samedit overflow), across opus, sonnet, and haiku legs.
