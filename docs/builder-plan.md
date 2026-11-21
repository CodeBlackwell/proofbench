# The eval builder: design and build plan

proofbench is meant to be a toolset for building evals of other agentic systems. Through
0.5.1 it is only the engine that runs an eval somebody already built by hand. This page
records the design agreed on 2026-11-20 and the order it is built in.

[Back to the README](../README.md)

## Contents

- [The goal](#the-goal)
- [Decisions](#decisions)
- [The eval folder](#the-eval-folder)
- [The gates](#the-gates)
- [Proposals still to review](#proposals-still-to-review)
- [Build phases](#build-phases)
- [Left out of v1](#left-out-of-v1)
- [Consequences to expect](#consequences-to-expect)

## The goal

Someone with an agentic system runs one skill and ends with an eval they can trust:

- The skill interviews them and writes the files.
- Commands decide every gate by exit code. The model never rules that an eval is sound.
- The eval lives in the repo of the system it tests, with the proof that its grader works.

## Decisions

Each line is a decision the owner made. A change to one is a change to this file.

**The product**

- **Audience:** the owner first, on their own systems. Strangers come later.
- **Shape:** one `/proofbench` skill that reads the state file and resumes at the first gate
  that is not green. Every gate is a subcommand of the Python CLI.
- **Packaging:** this repo becomes a Claude Code plugin as well as the PyPI package.
- **Deliverable:** a self-contained eval folder checked into the target system's repo.

**What is graded**

- **Outcomes:** both task kinds stay, a diff and an answer. Each task names one grader.
- **Command grader:** preferred wherever something can be run. The files it checks with are
  held back and copied into the clone only after the agent has finished.
- **LLM judge:** used only where nothing can be run.
- **The path:** proofbench defines one step log and ships a reader for the `claude` CLI.
  Any other system's adapter writes the step log itself.
- **Path grading:** fixed rule types in config, a script where those fall short, and an LLM
  judge that reads the path against a rubric.
- **The good path:** one recorded path per task is kept as an example for the path judge. It
  is not an answer the agent's path is scored against.

**What makes an eval trustworthy**

- **Known answers:** mined from history the owner holds, or prompted from them. An answer a
  model invented needs approval, one at a time.
- **Harvesters:** the skill writes one per target and commits it in that eval folder. No
  generic miner until two targets have needed the same one.
- **Four gates** block an eval from being called finished. See [The gates](#the-gates).
- **Controls:** a command builds the mechanical ones. The skill drafts the tricky ones and
  the owner approves each. The path judge faces the same check as the outcome judge.
- **State:** one file in the eval folder that only commands write.
- **Unchecked or stale evals:** `run` and `optimize` refuse them. An override flag runs
  anyway and marks the scoreboard as unchecked.
- **Judge input:** a hard size limit. Over it, the run stops and names the task.

**The existing engine**

- **Kept:** `optimize`, the crg-debug corpus and its records, the SWE-bench check of the
  shipped judge, the replay runner.
- **Dropped:** the tier by hops grid. A question line may still carry `tier` and `hops`, and
  any other field proofbench does not read; they are ignored.
- **Changed:** `optimize` keeps a rewrite only when it scores strictly better.

**The work**

- **First target:** tenex (`cyber-tenex-takehome`), built on a branch of that repo, not main.
- **What tenex's eval measures:** the answer names the planted users, hosts and detector, and
  every number in the answer appears in a tool result.
- **Second target:** triage-desk, rebuilt with the builder and compared with its hand-built
  eval.
- **Releases:** 0.6.0 for outcomes, 0.7.0 for the path, 1.0.0 after the second target.

## The eval folder

Proposed layout, inside the target repo:

```text
evals/<name>/
  proofbench.yaml     the config
  adapter.sh          starts the system headless; this is the runner or arm
  tasks/              question files, or the list of repo tasks
  harvest.py          collects real cases, when answers are mined
  judge.md            the outcome rubric, when a judge grades
  path-judge.md       the path rubric
  rules/              scripts for path rules the fixed types cannot express
  controls/           control results and the scores predicted for them
  paths/              the recorded good path for each task
  gates.json          the state file; only proofbench commands write it
  runs/               ignored by git
```

## The gates

| Gate | Passes when | Costs money |
|---|---|---|
| `adapter` | The adapter starts the system on one task and a result is captured | One agent run |
| `coverage` | Every answer class the config declares has tasks | No |
| `controls` | Each grader scores every control inside its predicted range | Judge calls only |
| `headroom` | The strongest model scores below 100% on the full eval | One full run |

- **Order:** the skill works through them top to bottom.
- **Paid gates wait:** the skill states an estimated cost and waits for a yes.
- **Predictions come first:** a control's expected range is written before it is graded.
- **Mechanical controls for an outcome:** the answer itself, nothing, half of it, unrelated
  noise.
- **Mechanical controls for a path:** a recorded real path as it was, with a required step
  removed, with steps reordered, and empty.
- **A command grader's controls are free:** the answer must pass and the starting state must
  fail.
- **Stale:** each gate records a hash of the files it covered. A changed file turns the gate
  stale, and a stale gate counts as not passed.

## Proposals still to review

These are the author's proposals, not the owner's decisions. Review them before they are
built.

- **Commands:** `proofbench controls` builds the mechanical controls, `proofbench check GATE`
  runs one gate and records it, `proofbench status` prints every gate and costs nothing.
- **No `init` command:** the skill writes the folder from templates it ships.
- **Override flag:** `--unchecked` on `run` and `optimize`.
- **Step log:** JSON lines, one step per line, in order:
  `{"tool": "...", "input": {...}, "result": "..."}`. The adapter writes it to the path in
  the `PROOFBENCH_STEPS` environment variable.
- **Path rules in config:** `called`, `never_called`, `before`, `max_steps` and `script`.
- **A rule script:** called as `SCRIPT STEPS_FILE ANSWER_FILE`. Exit 0 passes, exit 1 fails,
  and its one line of output is the reason.
- **Command grader in config:** a `check` command and a `hidden` list of paths to copy in.
- **Answer classes:** an optional `class` label per question and a `classes` list in config.
  What coverage means for repo tasks is settled on the first target.
- **Judge input limit:** a `judge_input_limit_kb` key. The default is set from sizes measured
  on the first target. The largest input seen so far was 868 KB and cost $4.50.
- **Path numbers on the scoreboard:** the share of tasks where every rule held, and the path
  judge's score.
- **The Claude reader** is written against the CLI's real stream output, not from memory.

## Build phases

Every phase ends with the tests passing and nothing committed or released until asked.

### Phase 0: clear the ground

Built on 2026-11-20.

- Drop the grid from `question.py` and `scoreboard.py`, with its tests and docs.
- Make `optimize` require a strictly better score.
- Move the hard-coded code-review-graph excludes out of `capture.py` into the `ignore` lists
  of `corpora/proofbench.yaml`.
- **Done when:** the crg-debug corpus still builds, triage-desk's configs still load, and
  `scoreboard.py` is under 200 lines.

### Phase 1: the outcome builder (0.6.0)

Built on 2026-11-21. tenex's eval passed all four gates the same day: 184 of 184 controls
graded as predicted, and the app's Sonnet model scored 30 of 42 (0.714) on the headroom run.
The gates cost $3.61 at API prices, all of it on the subscription. What was settled while
building it:

- **Where tenex's eval is.** `evals/console/` on the branch `proofbench-eval` of
  `cyber-tenex-takehome`, uncommitted.
- **tenex is asked through the `claude` CLI, on the subscription.** Its adapter stands where
  the app expects the SDK client. The app's loop, tools, fencing and citation checks run
  unchanged. The wire differs: tool schemas go in the system prompt and the model names its
  tool calls in a JSON reply, where production uses the API's native tool calls.
- **Two limits of the gate hashes, found on tenex.** A gate covers the runner file and not
  what that file calls, so editing `adapter.py` behind `adapter.sh` leaves the adapter gate
  reading as passed. And a gate covers every byte of the config, so fixing a comment turns
  all four stale.
- **One grader per corpus.** A pass rate and a recall have no shared average, so a config
  that mixes `check` tasks with judged tasks is refused. Each grader gets its own config.
- **Coverage is the same for both kinds.** A repo task takes a `class` key, as a question
  takes a `class` field.
- **The judge input limit defaults to 200 KB.** That is a placeholder until sizes are
  measured on tenex.
- **tenex's absence questions have an answer.** The console prints prose and cannot report
  an abstention, so "no such activity" is the expected answer `none` and the judge reads it.
- **tenex's generator plants every chain on the same first user.** Seven of its thirteen
  user questions share one answer, which the eval can only report.

- The judge input limit.
- The command grader with held-back files.
- `controls`, `check` and `status`, and the state file.
- The refusal in `run` and `optimize`, with `--unchecked`.
- The plugin manifest and the `/proofbench` skill.
- tenex, first pass: a driver script, a harvester over its ground-truth files, the
  questions, and the four gates green for answers.
- The README and the PyPI description rewritten around building evals.
- **Done when:** tenex's eval was built with the skill, `status` shows four green gates, and
  `run` executes it without the override.

### Phase 2: the path (0.7.0)

- The step log and the Claude reader.
- The rule types and the script rule.
- The path judge, its rubric, its controls and the recorded good path.
- tenex, second pass: the grounding rule, that every number in the answer appears in a tool
  result.
- **Done when:** tenex's eval grades both the answer and the path, and the path judge has
  passed its controls.

### Phase 3: the second target (1.0.0)

- Rebuild triage-desk's eval with the skill.
- Compare the effort and the scores with its hand-built eval of about 900 lines.
- Fix what a second system exposes.
- **Done when:** two systems carry an eval the builder produced, and neither needed a change
  to proofbench that was special to it.

## Left out of v1

- Conversations with a simulated user.
- Readers for other frameworks' trace formats.
- Generic miners.
- One grade from two graders.
- Answers invented by a model and accepted unreviewed.

## Consequences to expect

- **Every existing config is refused by `run`** until it has been through the builder. That
  covers triage-desk's seven configs, the crg-debug corpus, both demos and the CI smoke test.
  Each needs `--unchecked` in the meantime.
- **tenex is built in two passes,** because the path comes third in the build order.
- **triage-desk's `optimize` config has no held-out entry,** so it does not run on the
  current engine either. Phase 3 is where that gets fixed.

Three earlier questions are outside this design and still open: whether to keep the judge's
breakage rule, the hard-case READMEs that name the bug, and the item lists that have had no
review.
