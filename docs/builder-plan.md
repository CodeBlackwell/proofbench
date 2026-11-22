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
- **The docket,** decided 2026-11-21: a second skill, `/eval-docket`, modelled on vizardry's
  `/data-docket`. It asks the owner in multiple choice which claims about the system can
  honestly be tested, and on an eval that has tasks it puts each ambiguous task to them for a
  ruling. It writes one file per system, `evals/docket.md`. `/proofbench` reads it as
  guidance and offers it when there is none. It spends nothing and passes no gate.

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

Layout inside the target repo. `evals/docket.md` sits beside the eval folders, one for the
whole system:

```text
evals/docket.md       what can honestly be tested, and what was ruled out
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
| `headroom` | The strongest model scores above 0 and below 100%, each task asked once | One pass |

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

These were the author's proposals. The owner approved them as written on 2026-11-21. The
proposals made while building Phase 2 are listed under that phase and are still to review.

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

Built on 2026-11-21 and released as 0.7.0. tenex's eval passed all four gates again the same day,
now with a path: 218 of 218 controls graded as predicted, 34 of them for the path. The phase
cost about $7 at API prices, all of it on the subscription. tenex's second pass:

- **Headroom, with step logs:** Sonnet scored 31 of 42 (0.738) for $3.39.
- **Every attempt held every rule,** the 11 wrong answers included. The grounding rule
  checked 380 numbers across the 42 answers and found none invented. tenex's console reads
  the right data and then names the wrong thing: its misses are not grounding failures, and
  the path rules cannot see them.
- **The owner approved** two fixed rules beside the grounding rule (`called: list_findings`,
  and `before: [list_findings, get_detection]`), the path rubric, eight recorded paths (two
  per class) and seven hand-written path controls.
- **The controls gate cost $2.48,** after a pilot of 11 path controls that graded 11 as
  predicted. The path judge costs about $0.06 a control, twice the estimate: its prompt
  holds the path and the recorded path, each 10 to 20 KB.
- **No real attempt has been read by the path judge yet.** The headroom run was made with
  the rules alone, so the judge was not paid for before it had been checked. The first
  checked `run` produces tenex's `path_sound_rate`.
- **The grounding rule is weak on small whole numbers,** which nearly always appear
  somewhere in a result, and it takes a number from any result as grounding for any claim.

These are the author's choices, still to review:

- **The `path` key** holds `rules`, a `judge` rubric, or both. Rules apply to every task of
  the eval, not to one task.
- **`before: [A, B]`** holds when B was never called, or some A came ahead of the first B.
- **The path judge rules a path sound or not, 1 or 0.** It is shown the task, the step log
  and the recorded path, and never the answer. What an answer owes to its path is checked by
  a script, which is handed both.
- **A recorded path is a folder,** `paths/TASK/`, holding the step log and the answer file of
  one real attempt. A path control is the same folder shape under `controls/TASK/NAME.path/`.
- **The mechanical path controls follow from the declared rules.** `removed` takes out the
  tool of the first `called` rule and `reordered` turns round the first `before` rule. With
  no such rule, that control is not built, because nothing says what it should score.
- **A rule script that exits with anything but 0 or 1 stops the run.**
- **The stream is asked of `claude` only when the path is graded,** so an eval without a
  path runs exactly as it did.
- **A repo runner is told a log file outside the run folder,** which holds the answer diff.
- **What a gate covers changed.** The config is hashed as it parses, so a comment no longer
  turns a gate stale. What is under the `path` key is covered by `controls` alone, and
  `adapter` covers only whether the key is there, so changing how the path is graded does
  not cost another agent run. Every gate recorded by
  0.6.0 reads as stale once under 0.7.0.
- **With a path, `headroom` is checked before `controls`,** because recorded paths come from
  a full run.

- The step log and the Claude reader.
- The rule types and the script rule.
- The path judge, its rubric, its controls and the recorded good path.
- tenex, second pass: the grounding rule, that every number in the answer appears in a tool
  result.
- **Done when:** tenex's eval grades both the answer and the path, and the path judge has
  passed its controls.

### Phase 3: the second target (1.0.0)

Built on 2026-11-21 and not released. Triage Desk carries two evals the builder produced,
`evals/owner/` and `evals/intermittent/`, on the unpushed branch `proofbench-eval`. The
owner eval passes all four gates. The intermittent eval passes three and has not passed
headroom. What the second system showed:

- **The owner chose:** both evals at once, real failures only, no judge, no path, and a
  headroom gate that asks each question once.
- **Four changes to proofbench, none special to Triage Desk.** A question eval with no
  `judge` is graded by exact id alone and gets no words-only control. The headroom gate
  asks each task once, whatever `trials` says. `trials` and `concurrency` turn no gate
  stale. The headroom gate fails at a score of 0 as it does at 1.
- **What the gates caught in the hand-built eval.** Its 73 written questions have answers a
  model wrote, and Opus scores 100% on them, so they fail headroom. Its intermittent set
  held one class, which fails coverage; five `Steady` failures were mined to pass it. Its
  judge was never needed, and its rubric contradicted the words-only control.
- **What the gates did not catch, and now do.** On the intermittent eval Opus scored 0 of
  21 and declined 20. The answers are what a later re-run did, and nothing the agent is
  shown says what a later re-run will do. Headroom asked only for a score below 1, so the
  eval passed. An eval nobody can pass is worth as little as one everybody passes, so the
  gate now asks for a score above 0 too. The intermittent eval's records were reset and its
  headroom reads as not run. It stays unfinished until its answers can be reached from what
  the agent is shown, or the agent is asked to predict.
- **Every change to what a gate covers turns recorded gates stale once.** This phase's
  change did it to tenex, whose four gates cost $7.98 to earn again. The cover has changed
  in both releases since 0.6.0 and should stop changing at 1.0.0.
- **The path judge read real attempts for the first time, on tenex.** It called 31 of 42
  paths sound. All 11 it refused failed the same point: the console listed findings with no
  filter, was shown the first 50 of several hundred, and answered from those. The fixed
  rules cannot see that, and it corrects the Phase 2 note above: some of the console's
  misses do begin with not reading the right data.
- **The grounding rule failed 3 of 42 answers, and all three were false alarms.** Two wrote
  a number with a thousands separator, which the rule reads as two numbers. One converted
  bytes to megabytes and worked out a percentage. The first is a bug in the rule. The second
  is the rule as the owner stated it, and the owner's to keep or loosen.
- **One trial is noisy.** Sonnet scored 31 of 42 on tenex in the morning and 27 of 42 in the
  evening: four answers went from right to wrong and none the other way.
- **The comparison.** The hand-built eval is 886 lines written by hand: seven configs, a
  rubric, and four scripts. The builder's two evals are 86, two configs and two task
  builders, and reuse the repo's two miners, one of them extended by 20 lines. On the same
  25 owner questions Opus scored 0.467 over three trials by hand and 0.44 over one here.
- **One trial is not a third of the cost of three.** The second and third trials of a
  question read its log from the CLI's cache. Headroom cost $14.82 against the $5.70
  estimated by dividing an old three-trial run by three.
- **The hand-built `optimize` config has its held-out entry** and splits again. It runs
  only with `--unchecked`: it has been through no gate.

- Rebuild triage-desk's eval with the skill.
- Compare the effort and the scores with its hand-built eval of about 900 lines.
- Fix what a second system exposes.
- **Done when:** two systems carry an eval the builder produced, and neither needed a change
  to proofbench that was special to it.

### The builder on itself

Tried on 2026-11-21: a fresh Opus session ran `/proofbench` on this repo with no docket, the
owner answering its questions through a relay. It stopped before writing the eval, waiting on
the owner. What the trial showed:

- **It kept its rules.** It read before asking, started no paid gate, stated costs, and asked
  for approval of each task whose expected outcome it had written.
- **It chose to test the builder skill itself,** on three tasks cut from tenex and Triage
  Desk, graded by command, with the skill's three hard rules as path rules.
- **It found two gaps, both fixed the same day.** The controls gate graded no hand-written
  control on a task graded by command, and the cost of an executable repo runner was never
  read.
- **A live run of the fixes found a third gap,** also fixed: a repo eval could not name an
  adapter in its own folder, because the runner starts inside the clone.
- **The eval was then built and run,** in `evals/builder/`, uncommitted: two tasks come from
  a private repo. Building it cost about $11 of Opus. Its gates cost $3.73 against an
  estimate of $12 to $30.
- **Sonnet built tenex's eval unaided for $0.43,** and stopped for a yes before its first
  paid step. A notification arrived while it waited, and it said that was not an answer.
- **Opus scored 2 of 3 on headroom, and every session kept all three hard rules.** It built
  tenex's eval and Triage Desk's owner eval, where it left out every model-written question
  without being told to.
- **The task it failed is an ambiguous one.** On the one-class target the check wanted a
  folder that declared both classes and left one empty. The builder wrote nothing and put
  three facts to the owner first: no real case of the second class exists, four of the ten
  real cases are not failed tests, and the answer cannot be reached without the history
  tool. That is the unreachable answer the eval's author believed no builder could notice
  before a paid gate.
- **Ruled by the owner, 2026-11-21: stopping to ask was the right result.** The task's
  expected outcome was written by a model and was wrong. Under the ruling Opus scored 3 of
  3, so the eval is too easy for it and its recorded headroom pass does not stand.
- **The ruling cannot be put into effect by command.** The right result left no diff, and a
  task graded by command must fail on its starting state, which is also no diff. Nothing
  proofbench grades today holds a session's closing message: a rule script is handed the
  step log and the diff. Grading "it stopped and asked the right things" needs that message.
- **A builder cannot find the plugin's docs.** The skill says the formats are in the
  plugin's docs and names no path, so the session searched the whole disk for them.
- **Still open:** three tasks make a coarse headroom score, counting the ambiguous task as
  right would make it 3 of 3 and fail headroom, and nobody has tried scoring the gates
  themselves as a classifier, which costs almost nothing.

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
