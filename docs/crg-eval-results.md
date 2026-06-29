# crg-debug Eval: Opus vs Sonnet vs Haiku

Living record of the crg-debug debugging-skill evaluation across three driver models.
The easy five-repo phase is complete (see Results); the Tier-1 hard-case phase is now running
to break the easy-repo recall ceiling (see Tier-1 hard cases and Status). Rounds 1 to 3 evaluate
the prose **skill**; **Round 4** is the architectural turn the doc had been pointing at — enforcement
moved out of `SKILL.md` prose into a deterministic Workflow (`.claude/workflows/crg-debug.js`), where
gates are exit codes the script reads, not model claims.

## Objective

Measure how well the `crg-debug` skill finds and fixes planted bugs across a set of
debugging-interview repos, grade its fixes against each repo's published gold branch,
and use the gap to auto-improve the skill (closed loop). Run the same harness with three
different driver models to see whether the methodology, not just the model, carries the
result.

## Method (what we did)

* **Targets:** 5 debugging-interview repos, each with a ground-truth gold branch.

  | Repo | Default | Gold | Bug flavor | Gold diff size |
  |------|---------|--------|-----------|------------------|
  | debugging-challenge | master | working | ML correctness (reuse, softmax, reshape, double scaling) | 210 lines |
  | BugFix | main | solution | inverted/swapped logic (Python + C) | 420 lines |
  | ph2-raccoon-saloon-debugging-challenge | main | solution | React state/handlers/typos | 134 lines |
  | debugging-challenges | master | solution | JS scope / `=` vs `==` / undefined vars | 82 lines |
  | react-debug-practice | master | solution | React console errors, map/key props | 50 lines |

* **Grading:** diff-vs-answer LLM judge (no project execution, which sidesteps the
  TensorFlow/Postgres/MATLAB environment mess). The judge enumerates each planted bug from
  the answer diff, decides whether the agent's diff fixes the same root cause, and reports
  `recall` (fraction of planted bugs fixed) and `precision` (fraction of non-test agent
  changes that map to a real bug or are harmless). Agent-added test files are neutral by
  policy. **The judge is pinned to opus on all three legs** so the grader is a constant.

* **What the signal proves and does not:** recall/precision measure "matches the reference
  answer," not "passes a test suite." Precision as defined does **not** penalize large
  incidental churn if the judge deems it harmless (see Findings, react over-edit).

* **Closed loop:** baseline sweep, then a synth step feeds all grades plus the current
  `SKILL.md` to a model that proposes minimal skill edits, then an improved sweep applies
  the candidate to the (uniquely named) global skill and re-measures. A regression guard
  reverts the skill if improved macro recall drops below baseline.

* **Isolation:** each leg runs in its own directory, its own git worktrees of the 5 repos
  (detached, reset to pristine before every run), and its own uniquely named global skill
  so the legs never collide and never race the real `crg-debug`.

* **Headless driver:** `claude -p "/<skill>" --model <m> --dangerously-skip-permissions
  --output-format json --max-turns 200`, run from inside each repo worktree. Concurrency
  capped at 2 to 3.

### Three legs

| Leg | Debugger | Synth | Judge | Dir | Skill | Run script |
|-----|----------|-------|-------|-----|-------|------------|
| opus | opus | opus | opus | `.crg-eval/` | `crg-debug` | `run.sh` |
| sonnet | sonnet | sonnet | opus | `.crg-eval-sonnet/` | `crg-debug-sonnet` | `run-sonnet.sh` |
| haiku | haiku | **opus** | opus | `.crg-eval-haiku/` | `crg-debug-haiku` | `run-haiku.sh` |

Design note: on the haiku leg the synth is pinned to **opus** (not haiku), so a weak
debugger cannot also produce weak self-improvement. Only the debugging model varies. This
isolates "how well does haiku debug under this skill," at the cost that a low haiku score
could reflect either weaker debugging or weaker ability to drive the skill's parallel
orchestration (read the per-repo `claude.log` to attribute a miss correctly).

## Harness bugs found and fixed during the runs

All three surfaced at or near the synth step and were masked by whether the run had a TTY.
All are classic `set -euo pipefail` landmines that a dry-run cannot reach.

1. **`extract_json` choked on a prose preamble.** The synth model narrated before its JSON
   object, and the extractor only stripped code fences, so `jq` parsed `All four...` and
   died. Fix: slice from the first `{` to the last `}` (also subsumes fence stripping).
   Surfaced on the opus leg (interactive, so it reached the parse).

2. **`spin_wait` returned 1 when piped.** Its last line was `(( TTY )) && printf ...`; with
   `TTY=0` that returns 1, so the function returned 1, and `set -e` killed the caller before
   the parse. Fix: `return 0`. Surfaced on the sonnet leg (backgrounded, so `TTY=0`).

3. **Phantom "died at 4/5."** Not a harness bug: a watcher I wrote latched onto a `run_crg`
   worker subshell PID instead of the orchestrator, so when the worker finished it falsely
   reported the run as dead. The sonnet baseline had in fact completed. Fix: watch the
   orchestrator, not a worker.

4. **Oversized diff broke the judge, and the failure was silent.** On the haiku leg the
   `debugging-challenges` cell produced a 442,828 line `agent.diff`: haiku scaffolded a
   jsdom test harness, ran `npm install`, and the capture step (`git add -N . ; git diff`)
   swept the entire installed `node_modules` tree into the diff. The judge prompt embedding
   it was 22.8 MB, and the judge was invoked as `claude -p "$(cat prompt)"` — the whole
   prompt as a single shell argument. That exceeds `ARG_MAX` (1,048,576 bytes on macOS), so
   `exec` failed with "Argument list too long". The call was guarded by `|| true`, so the
   empty output flowed on: `extract_json` on an empty file emits nothing but `jq` exits 0, so
   the `|| die` guard never fired, an empty `grade.json` was written, and `aggregate` simply
   skipped the empty file. The harness then reported `macro_recall=0.662` as if complete,
   when it had silently averaged over 4 cells, not 5. Three compounding defects, three fixes,
   applied to all three scripts:
   * **Capture excludes installed-dependency / cache trees** (`node_modules`, `.venv`,
     `__pycache__`) via git pathspec, so the diff reflects source changes. Committed `dist/`
     is deliberately kept — rebuilding it is a real over-edit signal we want graded.
   * **Judge and synth prompts go in via stdin** (`claude -p ... < prompt`), never argv, so a
     large diff can never hit `ARG_MAX`.
   * **The empty-grade path now fails loud:** assert `judge.raw.json` is non-empty and the
     final `grade.json` has numeric recall/precision, else `die`. No more silent drops.

Both `run.sh` and `run-sonnet.sh` (and `run-haiku.sh`) now carry all four fixes.

## Results

### Baseline (recall / precision)

| Repo | planted | opus | sonnet | haiku |
|------|--------:|------|--------|-------|
| debugging-challenge | 7 | 1.00 / 1.00 | 1.00 / 1.00 | 0.857 / 1.00 |
| BugFix | 14 | 1.00 / 1.00 | 1.00 / 1.00 | 0.79 / 1.00 |
| ph2-raccoon-saloon | 17-18 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| debugging-challenges | 1 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| react-debug-practice | 2 | 1.00 / 1.00 | 1.00 / **0.83** | **0.00 / 0.00** |
| **macro** | | **1.00 / 1.00** | **1.00 / 0.966** | **0.729 / 0.80** |

The haiku `debugging-challenges` cell is the recovered one: its baseline grade was the empty
cell from harness bug 4. The fix strips `node_modules` from the saved diff (442,828 lines to
592) and re-grades; the recovered grade is 1.00 / 1.00 (haiku fixed the one real functional
bug; the answer diff's second "bug" was cosmetic README reformatting the judge correctly
discounted). So haiku's honest baseline macro is **0.729 / 0.80 over all five cells**, not the
0.662 / 0.75 the broken harness reported over four.

### Improved (after closed-loop skill edit)

| Leg | baseline macro recall / precision | improved macro recall / precision | kept or reverted |
|-----|-----------------------------------|-----------------------------------|------------------|
| opus | 1.00 / 1.00 | _not run (ceiling, decision open)_ | n/a |
| sonnet | 1.00 / 0.966 | 0.986 / 0.976 | **reverted** (recall regressed −0.014) |
| haiku | 0.729 / 0.80 | 0.929 / 1.00 | **kept** (recall +0.199, precision +0.20) |

Haiku improved, per repo: debugging-challenge **0.714 / 1.0** (regressed from 0.857), BugFix
**0.93 / 1.0** (up from 0.79), ph2 1.0 / 1.0, debugging-challenges 1.0 / 1.0, react-debug-practice
**1.0 / 1.0** (up from 0.0 / 0.0). The opus-authored synth edit drove a real, kept lift, but the
gain is concentrated in react (0.0 to 1.0) and BugFix, and partly offset by a debugging-challenge
regression. The harness originally printed lift +0.267 because its baseline silently averaged
four cells; against the honest five-cell baseline the lift is **+0.199 recall, +0.20 precision**.

Sonnet improved, per repo: debugging-challenge 1.0/1.0, **BugFix 0.93/0.88** (regressed),
ph2 1.0/1.0, debugging-challenges 1.0/1.0, **react-debug-practice 1.0/1.0** (precision
fixed from 0.83, the minimal-diff guard's exact target). Net: the candidate fixed the
react over-edit it was designed to fix, but coincided with a BugFix dip, so macro recall
fell 1.0 to 0.986 and the regression guard reverted the skill to pristine (verified).

### Synthesis anatomy (how each leg improved the skill)

Each synth call was fed the same inputs: all per-repo `grade.json` files plus the current
`SKILL.md`. It returned a full edited `SKILL.md` plus a changelog. The pristine skill is 160
lines; the candidates landed at opus 176, sonnet 163, haiku 177. Below is every edit, where it
landed, and the observed miss that motivated it. Candidate files: `.crg-eval*/SKILL.md.candidate`.

**opus synth (3 edits, +16 lines).** Opus missed nothing in baseline, so two of its three edits
are preventative reasoning rather than evidence:
* *Common bug-class checklist* (new Cross-cutting subsection, run over every function in a
  discovery slice): inverted boolean/return, flipped comparison/sort, double-applied transform,
  off-by-one bound, broken swap, wrong operator, undefined/misspelled identifier, wrong call
  signature, state-setter no-op, JSX literal-vs-interpolation. Preventative.
* *Extra scrutiny on untested files* (folded into the Phase 2 discovery-agent instruction):
  inverted logic and off-by-one slip past where no test flags them. Preventative.
* *Minimal-diff rule* (new): confine each edit to the lines that fix the named bug. Do not
  re-emit build artifacts, bump deps, or reformat. The only evidence-backed opus edit, targeting
  the react over-edit opus itself committed (rebuilt `dist/bundle.js`, bumped inlined React).

**sonnet synth (1 edit, +3 lines).** Sonnet was at the recall ceiling, so it had a single
precision miss to learn from and made exactly one edit:
* *Generated/compiled artifacts are never directly edited* (added under the False-positive
  guard): `dist/`, `build/`, `out/`, lockfiles, `*.bundle.js`, `*.min.js`, transpiled `.js`
  beside `.ts`. A wrong generated file is a symptom of a source bug. Routes any such candidate
  to a source fix. Targets the one observed false positive (react `dist/bundle.js`).

**haiku synth (opus-authored, 4 edits, +17 lines).** Haiku produced real, diverse misses, so
this is the most grounded candidate. Every edit names the exact baseline failure it targets:
* *Mandatory full-file coverage* (Phase 1): enumerate EVERY in-scope source file via
  `git ls-files`, not just hubs, and tag each to a concern. Targets the BugFix leaf files
  (`mergesort.c`, `quicksort.c`) the sweep compiled but never opened.
* *Bug-class checklist* (Phase 2, run against every function read): undefined/misspelled
  reference, off-by-one/wrong-start index, inverted boolean, train/test mode divergence (dropout
  active at inference), double-applied transform, swapped/no-op operation. Targets the clustered
  recall misses (react `data`/`someFunc`, BugFix start index, debugging-challenge dropout-at-eval).
* *Residual pass opens every unclaimed source file* (Phase 2): leaf and non-hub files are where
  planted bugs hide while hubs draw attention. Reinforces the full-file coverage edit.
* *Fix source, never generated output* (stated in Phase 3, the False-positive guard, and the git
  policy): editing `dist/`, a bundle, or a lockfile is not a fix and counts as a precision
  regression. Targets react's 0.0 precision (it edited `dist/bundle.js` and regenerated
  `package-lock.json` while the buggy source survived).

### Convergence is the adoption signal

Read across the three legs, the edits stratify by how many independently derived them. That
count, not any single leg's confidence, is the safest filter for what to fold into the real
`crg-debug`:

| Edit | opus | sonnet | haiku | verdict |
|------|:----:|:------:|:-----:|---------|
| Never edit generated artifacts (minimal-diff) | yes | yes | yes | **3/3 — adopt** |
| Bug-class checklist (inverted bool, off-by-one, double transform, undefined ref) | yes | no | yes | 2/3 — strong |
| Extra scrutiny on untested / leaf files | yes | no | yes | 2/3 — strong |
| Full-file enumeration + residual opens every file | no | no | yes | 1/3 — hypothesis |

The generated-artifact guard is the one edit all three reached independently, and it is the only
edit that is evidence-backed on every leg (each leg observed the over-edit it guards against). The
bug-class checklist is the next strongest: opus derived it preventatively and haiku derived it from
real misses, so a careful reasoner and an empirical one converged on nearly the same list. Haiku's
full-file enumeration is weak-driver scaffolding that the strong models did not need.

### How to synthesize (the method this surfaced)

* **Synth quality is bounded by the quality of the gaps you feed it.** Sonnet at the ceiling had
  nothing to learn, over-fit a single edit, and that edit traded against run-to-run noise, so the
  guard reverted it. Haiku, with real and varied misses, produced specific grounded edits that
  held a kept lift. A weak driver is not a liability for the loop; it is the only source of signal.
* **Every adopted edit must cite the failing case.** All three candidates do (for example "a
  baseline run scored zero by editing `dist/bundle.js`"). An edit with no named miss behind it is
  a guess, however reasonable.
* **Use cross-leg convergence, not single-leg confidence, as the merge gate.** Fold in what at
  least two independent legs derived; treat single-leg edits as hypotheses to test, not to ship.
* **Watch n=1 even on a kept lift.** Haiku's +0.199 is real at the macro level but concentrated in
  react 0.0 to 1.0, which a single stochastic run cannot distinguish from variance. Convergence
  plus a confirming re-run is what would promote it from "kept" to "trusted".

## Findings and interpretation

* **The easy-repo ceiling.** Opus scored a perfect 1.00/1.00 and sonnet 1.00/0.966. On
  these repos the strong models miss almost nothing, so the skill-improvement loop has very
  little to learn from on the recall axis. This is exactly why the haiku leg matters: a
  weaker debugger is the only one likely to generate real misses to learn from.

* **The one grounded lesson (precision, not recall).** The judge scored react-debug-practice
  at precision 0.83 on sonnet and called out a real over-edit on opus too: the agent rebuilt
  the committed `dist/bundle.js` (a 16k line minified bundle for a 2 bug repo) and bumped the
  inlined React version as a side effect. The grading metric is blind to this churn unless
  the judge flags it, which is itself a lesson: the precision metric should also weigh diff
  size. The synth's minimal-diff guard is the corrective both opus and sonnet converged on.

* **The regression guard works, and n=1 is the real limitation.** On the sonnet leg the
  candidate fixed its target (react precision 0.83 to 1.0) but coincided with a BugFix dip,
  netting macro recall 1.0 to 0.986, so the guard reverted the skill. The safety behavior is
  correct. But the eval runs one sample per cell and the debugger is stochastic, so a 0.014
  macro swing is within run-to-run noise. The react precision fix is believable (it maps to
  the guard's intent); the BugFix regression may be variance. The harness cannot currently
  separate a small real lift from noise. Repeated runs per cell (best-of-N or averaged) are
  needed before any sub-0.05 delta can be trusted.

* **An eval that fails open lies.** The most important finding is about the harness, not the
  models: when the haiku judge call silently produced no output, the harness wrote an empty
  grade, the aggregator skipped it, and the scoreboard reported a confident `macro_recall=0.662`
  that was secretly an average of four cells, not five. A measurement system must fail loud or it
  will quietly tell you a wrong number you have no reason to distrust. The fix makes every empty
  or non-numeric grade a hard `die`. The corrected five-cell baseline (0.729) is materially
  different from the broken one (0.662), and the reported lift fell from +0.267 to an honest +0.199.

* **A macro-only guard hides per-repo regressions.** The haiku improved skill was kept on macro
  recall, yet `debugging-challenge` regressed 0.857 to 0.714 under the same edit. The guard is
  correct as a global safety net but blind to local trades; a stricter loop would also flag any
  cell that regressed beyond noise, not just the average.

* **What still limits the experiment.** The repo set is too easy to drive recall lift, the
  precision metric undercounts churn, and there are no repeat runs to average out model
  stochasticity. Most informative future changes: harder targets (subtle multi-file bugs),
  a churn-aware precision signal, and N repeats per cell. The first of these is now underway:
  see "Tier-1 hard cases" for three real upstream bugs added to break the easy-repo ceiling.

## Tier-1 hard cases (the discriminator set)

The five baseline repos top out: opus and sonnet score a perfect or near-perfect recall, so
the loop has almost nothing to learn on the recall axis (see Findings, "the easy-repo
ceiling"). The fix is harder targets. We added three, chosen to be the opposite of the
interview repos in every way that matters: real production bugs from CPython and sudo, each
of which took experts, formal verification, or years of latency to find, and none of which
is a textbook teaching example a frontier model has memorized.

### The three cases

| Case | File | Bug class | Gold diff | Upstream fix / parent |
|------|------|-----------|----------:|-----------------------|
| cpython-timsort | `Objects/listobject.c` | `merge_collapse` run-stack invariant only checks the top three runs, not four | +2 / −1 (14 lines) | `b808d590` / `83704963` |
| cpython-asyncio-cond | `Lib/asyncio/locks.py` | `Condition.notify()` vs `Task.cancel()` lost wakeup | +63 / −49 (224 lines) | `6b53d5fe` (gh-112202) / `96bce033` |
| sudo-baron-samedit | `plugins/sudoers/sudoers.c` | `set_cmnd` escape-loop off-by-one heap overflow (CVE-2021-3156) | +18 / −5 (58 lines) | `1f863857` / `c4d38408` |

The timsort bug is the canonical example: a latent stack-size invariant violation that sat in
CPython (and Java, and Android) for years and was found only by formal verification (de Gouw
et al., 2015), not by tests. The fix is two lines. Finding it requires reasoning about the
invariant the merge loop is supposed to maintain, which is exactly the discrimination we want.

### Why these are hard discriminators (and Heartbleed is not)

The point is not "famous CVE." goto-fail and Heartbleed are famous, and a frontier model
recognizes them on sight, so they measure recall of training data, not debugging. These three
are the opposite: the bug is a single subtle line buried in a 600 to 3,000 line real source
file, the surrounding code is production-grade and gives no hint, and the correct reasoning is
about an invariant or a race, not a typo. A model has to actually find it.

### Single-artifact design (how they map onto the harness with no new machinery)

Each case is a self-contained git repo whose default branch `buggy` is the **real upstream
parent commit** (`fix~1`) and whose `origin/fixed` branch is the **real upstream fix commit**.
That is the entire trick: buggy state and gold answer are two adjacent real commits, so the
existing harness contract (default branch = buggy, `origin/<answer>` = gold, gold diff =
`git diff buggy..origin/fixed`) applies unchanged. No benchmark Docker, no build, no execution
— the asyncio case is pure Python and the C cases are graded on the diff, same as every other
cell. The gold diffs are the upstream `+/−` stats line for line (verified against the commits),
so they are genuine reference fixes, not reconstructions from memory.

The judge needs no change: it already grades **semantic root-cause equivalence**, not textual
overlap (`judge.prompt.md` lines 12-13). Each gold diff is *a* correct fix, not the only one, so
a functionally equivalent fix in a different spot still scores as recall. The asyncio gold was
scoped to `Lib/asyncio/locks.py` only — the upstream commit also touched docs/tests/NEWS, which
are neutral by the harness's own rule.

### Wiring

Three entries appended to the `REPOS` array in all three run scripts:
`cpython-timsort:buggy:fixed`, `cpython-asyncio-cond:buggy:fixed`,
`sudo-baron-samedit:buggy:fixed`. Built once as canonical repos, then `git clone`d (local file
clone) into each leg's repo dir so every leg gets its own `origin/fixed` ref. The eval set is
now eight cells: five easy plus three hard.

### Results (recall / precision, run with `--only` per case)

| Case | gold lines | opus | sonnet | haiku |
|------|-----------:|------|--------|-------|
| cpython-timsort | 14 | _not run_ | **1.00 / 1.00** | **0.00 / 0.00** |
| cpython-asyncio-cond | 224 | _not run_ | 1.00 / 1.00 | 1.00 / 0.67 |
| sudo-baron-samedit | 58 | _not run_ | 1.00 / 0.80 | 1.00 / 1.00 |
| **macro (tier-1)** | | _not run_ | **1.00 / 0.93** | **0.67 / 0.89** |

**The discriminator works.** On `cpython-timsort`, sonnet scored 1.00 / 1.00 and haiku 0.00 /
0.00 — a clean separation the five easy repos never produced (there sonnet and haiku differed by
at most a fraction). Sonnet's fix is **semantically identical to the gold answer**: it added the
exact missing disjunct `(n > 1 && p[n-2].len <= p[n-1].len + p[n].len)` to the invariant check,
having reasoned about the run-stack invariant rather than pattern-matching the nearest `if`.
Haiku, on the same block, edited the wrong line and broke correct logic. Same skill, same case,
opposite outcome — which is exactly what a discriminating eval cell is supposed to show.

Haiku still cleared the other two: `sudo-baron-samedit` 1.00 / 1.00 (found the CVE-2021-3156
off-by-one) and `cpython-asyncio-cond` 1.00 / 0.67 (fixed the lost-wakeup race). The asyncio
precision dip is a **new false-positive class**: haiku committed `crg_scope_analysis.json`, a
271-line scratch artifact written by the debug tooling itself, into the fix diff. That is not a
`dist/` bundle (the case the existing artifact guard covers) — it is the tool's own working file
leaking into the result. Worth a harness fix (strip known tooling scratch files in the capture
step, like `node_modules`) and/or a skill-prompt line ("never commit analysis scratch files").

Sonnet swept all three on recall (1.00 each), confirming every case is solvable and that the
gap to haiku is a real capability difference, not an unfair case. Sonnet's asyncio precision is
1.00 (it fixed the same race without leaking the tooling scratch file haiku committed), and its
sudo precision is 0.80 (minor incidental churn). Opus leg not yet run. **Net: the hard cases
discriminate cleanly at the haiku/sonnet boundary but sonnet still ceilings on recall, so for
the closed loop's purpose — generating real misses to learn from — haiku-on-timsort is the
prize specimen.**

#### A/B test of the prompt fixes on haiku (FAILED — reverted)

Per the "use the weakest model to verify the strongest prompt" method, we hand-authored the two
candidate edits above into `crg-debug-haiku`'s body and re-ran all three cases against the
archived pristine-prompt baseline. The result is a clean negative, and catching it is the point
of verifying on the weak model:

| Case | pristine prompt | edited prompt | outcome |
|------|-----------------|---------------|---------|
| cpython-timsort | 0.00 / 0.00 | 0.00 / 0.50 | invariant gate did NOT reach the fix — misdiagnosed a *different* line (`else if`→`if`) |
| cpython-asyncio-cond | 1.00 / 0.67 | **0.00** / 1.00 | recall **regressed** (no longer fixes the race); scratch-file rule did clean precision |
| sudo-baron-samedit | 1.00 / 1.00 | **0.33** / 1.00 | recall **regressed** hard |

The invariant-gate edit failed its one job (timsort recall stayed 0) and coincided with recall
regressions on the two cases haiku previously passed. The scratch-file rule worked in isolation
(precision went to 1.00 everywhere, no `crg_scope_analysis.json` leak), but a precision win cannot
offset losing recall on solved cases. Per the promotion gate — *an edit ships only if it
measurably helps haiku without regression* — the candidate is rejected. The `crg-debug-haiku`
body was reverted to its pre-A/B backup (`SKILL.md.bak.manual-abtest`, verified byte-identical),
the pristine baseline restored into `runs/baseline/`, and the A/B numbers archived under
`runs/baseline-tier1-abtest/` for the record.

**Two lessons.** (1) A plausible, evidence-cited prompt edit is still a hypothesis until the weak
model runs it; verifying on haiku stopped a bad edit from reaching the canonical prompt — exactly
the value the weak-model rig exists to provide. (2) **n=1 cannot attribute the regressions.** The
asyncio 1.00→0.00 and sudo 1.00→0.33 drops could be the gate causing analysis-paralysis/over-revert
in a weak model, or plain haiku stochasticity — a single sample per cell cannot separate the two.
This is the doc's standing "need N repeats per cell" limitation biting in practice: before any
prompt edit is judged, each cell needs several runs so a real effect is distinguishable from
variance. The next iteration should re-run the pristine baseline 3-5× per case to establish the
noise band first, THEN test an edit against it.

First cell to land confirms the design works: **haiku produced a 13-line diff on the timsort
case and scored 0.00 / 0.00** — it changed code but did not fix the `merge_collapse` invariant.
That is the first non-trivial recall miss the eval has produced on a strong-ish driver, i.e.
exactly the signal the easy repos could not generate. Remaining cells filling in as the sonnet
and haiku legs run (opus leg not yet run).

#### Haiku's failure mode on timsort (and a prompt-fix to explore)

0.00 / 0.00 here is worse than an empty diff, and the shape of the failure is the lesson.
Haiku's localization was perfect: it found `Objects/listobject.c`, the `merge_collapse`
function, and the exact `if` block. Then it edited the **wrong line inside the right block**:

```c
-            if (p[n-1].len < p[n+1].len)   // inner merge-target tie-break (correct as-is)
+            if (p[n-1].len > p[n].len)     // haiku's change: rewrites correct logic, wrong
```

The real bug is one level up — the `while`-loop invariant check is missing its second clause
`(n > 1 && p[n-2].len <= p[n-1].len + p[n].len)`. Haiku never touched it. So recall is 0
(planted bug unfixed) **and** precision is 0 (its one edit was not harmless — the judge found it
rewrote correct tie-break logic into incorrect logic, introducing a new defect). An empty diff
would have scored recall 0 / precision ~1.0; haiku scored worse by confidently shipping a wrong
fix. The pattern: it matched "something looks off in this `if`" and acted, instead of reasoning
about the invariant the loop must maintain.

**Prompt-modification idea (to test later, do not ship yet):** before editing, require the
driver to state the invariant or contract the suspect code must uphold, then verify the line it
is about to change is the actual cause of the violation rather than merely adjacent to it. A
"name the invariant, then confirm the edited line is the cause, not a neighbor" gate would
target exactly this confident-misdiagnosis failure. This is a hypothesis; whether it helps haiku
without hurting throughput needs an A/B re-run on this cell. Note it now, validate before adoption.

## Round 2 — trace-and-reverify loop (band-vs-band protocol)

### Why a second round, and what we changed

The A/B above failed (see that section): the candidate edits lifted precision on every case but
dropped recall on two cases haiku previously passed, and never moved the target (timsort stayed
0.00). The post-mortem (full analysis in the investigation log below) attributed the failure to
the *shape* of the edit, not bad luck: both edits pulled toward caution, and the
"confirm-the-cause-line-or-revert" gate in particular made an already-weak model edit less and
revert more, which on a weak model converts straight into lost recall. The all-three-cases
same-direction shift (precision up, recall down/flat) is what argues the effect was systematic.

**Decision (user-directed): keep all three cases, replace the confirm-or-revert gate with a
concrete-input trace-and-reverify loop, keep the scratch-file rule, and measure with repeats.**

### Investigation log (why the last change failed — grounded in the diffs)

* **asyncio (pristine 1.00/0.67 → A/B 0.00/1.00).** The pristine run edited `locks.py` and fixed
  the real lost-wakeup (re-deliver the notification in `wait()`'s cancel path). The A/B run
  scattered across `Lib/__init__.py`, `asyncio/__init__.py`, `exceptions.py`, `mixins.py` plus
  test stubs, made only a *harmless-but-ineffective* `list(self._waiters)` copy in `locks.py`, and
  missed the root cause entirely. Different, worse diagnosis — recall lost.
* **sudo (pristine 1.00/1.00 → A/B 0.33/1.00).** This case has THREE planted bugs: the primary
  trailing-backslash over-read plus two defense-in-depth fixes (`MODE_RUN` guard, explicit
  destination bounds checks). The A/B run fixed *only the primary and stopped* (1 of 3 = 0.33).
  The grade note: it "did not add the answer's two defense-in-depth/secondary fixes." The
  "find THE single cause line, don't touch neighbors" framing told it to stop after one.
* **timsort (0.00 → 0.00).** The gate did not get haiku to the real fix (augment the FIRST
  invariant clause with the `p[n-2]` term); it just misdiagnosed a *different* line (`else if`
  → `if`). **Naming an invariant in prose does not supply the reasoning to translate it into the
  correct code change.** The capability gap is real; a sentence does not close it.
* **The cross-case pattern.** Precision rose or held everywhere; recall fell or held everywhere.
  A precision intervention aimed at a recall problem made the weak model timid — fewer edits,
  more reverting, stop-at-first-cause — which is the opposite of what these cases need.

### Considerations weighed (and the calls made)

* **Skip the C cases?** Tempting, because the trace-and-reverify loop's "re-execute" step is only
  *real* on the pure-Python asyncio case (CPython/sudo can't be cheaply built, so the loop
  degrades to hand-simulation). Rejected: timsort is the one *clean, low-variance* discriminator
  (haiku 0.00 both runs, sonnet 1.00), and grading is diff-based so it does not need the skill to
  build CPython to produce a score. Dropping it would gut the signal and leave only asyncio, the
  *flickeriest* cell (haiku scored 1.00 then 0.00 across two runs). **Kept all three; timsort and
  sudo validate the hand-trace path, asyncio validates the real-execution path.**
* **Uniform prompt.** Per the standing principle (one canonical prompt across all CRG versions;
  the weakest model verifies the strongest prompt), this edit is developed and verified on the
  `crg-debug-haiku` body as the test vehicle. It is promoted to the single canonical body (and all
  four skill files, byte-identical modulo `name:`) ONLY after it clears the promotion gate. The
  pre-existing body drift (sonnet lost the bug-class checklist opus kept) is reconciled in the
  same promotion pass — not before, to avoid confounding the measurement.
* **n=1 is untrustworthy.** The A/B could not separate a causal regression from haiku
  stochasticity. This round fixes that with a **band-vs-band protocol** before any promotion.

### The change (exact)

Two edits to the canonical body. Neither contains "revert if unsure" — the failure mode we are
removing.

1. **Keep the scratch-file rule** (the one clean, recall-neutral precision win from the A/B),
   under the git & safety policy: never leave tool-generated scratch/analysis files
   (`crg_scope_analysis.json` etc.) in the working tree; delete or `.gitignore` before finishing.
2. **Replace the confirm-or-revert gate with a capability scaffold** — a new Cross-cutting
   subsection, *Invariant & algorithmic bugs — trace a concrete input, then re-verify*:
   1. Name the invariant/contract the code must maintain.
   2. Construct a concrete input that violates it under the current code (actual values).
   3. Hand-execute the function step by step on that input; the statement where the invariant
      first breaks is the fix site — not the line that merely looks suspicious.
   4. Apply the fix, then re-verify on the same input: run the test if the project builds,
      otherwise re-execute the trace by hand and show before → after.
   5. Then look for a SECOND violating input; if one exists it is another in-scope bug — fix it
      too. Do not stop at the first fix.

   Step 3 supplies the reasoning the prose gate only gestured at (hand-tracing locates the exact
   divergence). Step 4 makes a wrong edit bounce back instead of shipping. Step 5 directly repairs
   the sudo multi-fix regression. The scaffold raises capability without lowering edit-willingness
   — the axis the A/B got wrong.

### Method

* **Band-vs-band, N=3 repeats per case, all three cases, haiku as the verifier.**
  * **Pristine band** (`runs/round2-pristine/<case>/grade.rep{1,2,3}.json`): the current pristine
    body, 3 repeats per case, to measure the noise floor — especially for the flickery cells.
  * **New band** (`runs/round2-newprompt/<case>/grade.rep{1,2,3}.json`): the edited body, same 3×3.
* **Judge held at opus, same as every other run.** Only the debug prompt changes between bands.
* **Promotion gate:** the edit ships to the canonical prompt only if the new band's recall is
  above the pristine band on the target (timsort) AND does not regress below the pristine band on
  asyncio/sudo, judged against the measured noise, not a single sample. N=3 is a minimum band;
  N=5+ would firm it up and is the next step if the N=3 read is ambiguous.
* **Caveat recorded up front:** on the C cases the re-verify step is hand-simulation, which a weak
  model can do incorrectly — so this is a recall *aid*, not a guarantee, and the band is how we
  tell an aid from noise.

### Results (band-vs-band)

| Case | pristine band (rep1 / rep2 / rep3) | new band (rep1 / rep2 / rep3) | read |
|------|-----------------------------------|-------------------------------|------|
| cpython-timsort | _running_ | _pending_ | — |
| cpython-asyncio-cond | _running_ | _pending_ | — |
| sudo-baron-samedit | _running_ | _pending_ | — |

Pristine band running now (`runs/round2-pristine/`); new band runs after the body edit. Table
fills as reps land.

> **Superseded by Round 3.** The Round 2 prompt edit was never promoted: before the band
> finished we changed tack. Instead of editing *what the agent is told*, Round 3 changes *how
> many chances it gets and whether it keeps its own context* — and tests that on the pristine
> prompt, so iteration is the only variable. The band-vs-band protocol above remains the
> template for any future prompt-edit round.

## Round 3 — iterative session-resumed loop (real-user-style iteration)

### Why this round

A real user does not take a one-shot suggestion and stop. They keep the same conversation
open: the agent accumulates its own findings across turns, and often cracks by the third pass
what it missed on the first. Single-shot grading measures the opposite — a cold, contextless
attempt that biases toward "here is a copy-paste suggestion." Round 3 measures whether *just
letting the session continue* lifts recall, with the prompt held pristine so iteration is the
only thing that changed.

### The change (harness, not prompt)

`run_crg` now runs up to N tries (default N=3, `CRG_EVAL_MAX_ITERS`) that continue ONE session:

* **Try 1:** `claude -p "/crg-debug-haiku" --session-id <uuid>` — the skill, exactly as before.
* **Tries 2..N:** `claude -p "<nudge>" --resume <uuid>` — same session, full prior context carried.
  Verified in isolation: a token planted in try 1 is recalled verbatim in a resumed try 2.
* **The nudge is neutral and leak-free** — no bug count, no answer hint: *"Re-examine for any
  remaining bug; re-verify each change by tracing a concrete input; do not revert a correct fix.
  If confident the code is fully correct, end with DEBUG_COMPLETE; otherwise continue."*
* **Early exit** when the agent emits `DEBUG_COMPLETE`, so a truly-fixed case does not burn the full N.
* Each try's diff is snapshotted (`agent.try{i}.diff`); the **final** state is graded exactly as
  before, and `.tries` records how many passes it used.

### Why this design, not the alternatives

* **Session resume, not a re-fed notes file.** Resuming the real session is the faithful analog
  of a user continuing a chat. A separate notes file is a second, divergent memory that can
  contradict the transcript — one source of truth is simpler and more honest.
* **Agent self-declared done, not a judge/test oracle, as the stop signal.** The judge knows the
  answer; feeding its recall back would leak the key and is not how a real user works. Running
  real tests would force the C build we deliberately avoid. So the loop is bounded by N and exits
  early only on the agent's own confidence — which means a confidently-wrong weak model can still
  stop early at try 2. That is a real, measurable failure mode, not a harness bug.
* **N is a ceiling, not a target.** The goal is to *allow* the session to continue so it may figure
  it out by N, not to force N passes.

### Three cells (iteration AND the prompt edit, each isolated)

The instruction was to do *both*: edit the prompt **and** iterate. To keep attribution honest we
run three cells that change one thing at a time:

1. **single-shot pristine** — one cold pass, pristine prompt (`runs/baseline-singleshot-pristine/`).
2. **iterative pristine** — N=3 session-resumed, pristine prompt (`runs/iter-pristine/`). Isolates
   the effect of *iteration alone*.
3. **iterative + edited** — N=3 session-resumed, prompt + three edits (`runs/iter-edited/`):
   (a) the trace-and-reverify subsection (a recall *aid*: name invariant → build a violating witness →
   hand-execute to the cause line → re-verify the witness → look for a second); (b) the scratch-file
   rule; (c) **"no RED, no edit"** — the TDD gate hardened into a hard stop after the cell-2 timsort
   post-mortem below: you must see a real failing test before editing, and a test that runs against an
   *unbuilt* interpreter is not a RED. Isolates the *prompt edits on top of* iteration.

Both iterative cells run from one sequential driver into separate archive dirs (no shared-dir race —
the failure mode that corrupted the first attempt was three eval loops writing `runs/baseline/` at
once). Skill set pristine for cell 2, swapped to the edited body for cell 3, judge pinned to opus
throughout. Each cell reports final recall/precision **and** `.tries` (passes used) + per-try diffs,
so we can see whether recall climbed across passes or the agent stopped early.

### Results

| Case | 1. single-shot pristine | 2. iterative pristine | 3. iterative + edited | read |
|------|-------------------------|-----------------------|-----------------------|------|
| cpython-timsort | 0.5 / 1.0 | 0.0 / 0.5 (2 tries) | **0.0 / 0.0** (2 tries) | edit **regressed** precision 0.5 → 0.0 |
| cpython-asyncio-cond | 1.0 / 0.67 | 1.0 / 1.0 (2 tries) | 1.0 / 1.0 (2 tries) | held at ceiling |
| sudo-baron-samedit | 1.0 / 1.0 | 1.0 / 1.0 (2 tries) | 0.33 / 1.0 (2 tries) | **same fix both cells** — recall swing is judge noise, not behavior (see below) |

**sudo recall swing is grading noise, not a behavioral regression.** The agent applied the *same*
canonical root-cause guard (`from[1] != '\0'`, the CVE-2021-3156 fix) in both iterative cells. The
number moved because the opus judge **decomposed the answer key differently across runs**: cell 2 it
scored the CVE as **1 planted bug** (fixed → 1.0); cell 3 it split the same upstream patch into **3**
(root cause + two defense-in-depth additions: per-write bounds checks and MODE_RUN gating of the
unescape loop) and counted 1 of 3 → 0.33. Same denominator instability the timsort single-shot column
shows. So sudo is *stable* in behavior; only timsort is a real, attributable regression.

Single-shot column is the most recent pristine single-shot sample; timsort's single-shot recall
flickers (0.0–0.5 across samples), so reads are judged against that noise, same caveat as Round 2.
Promotion gate (unchanged): the edited prompt ships to all four canonical skills only if cell 3
beats cell 2 on timsort with no regression on asyncio/sudo, judged against that noise.

### Verdict — edit REJECTED, not promoted

Cell 3 fails the gate. On the only case with headroom (timsort) the edit did not lift recall (0.0 →
0.0) and *regressed* precision (0.5 → 0.0). asyncio held at ceiling; sudo's recall number moved
1.0 → 0.33 but that is **judge-decomposition noise, not behavior** — the agent made the identical
root-cause fix in both cells (see the sudo note in Results). No case improved, one regressed.
So the three edits do **not** ship to the four canonical skills. The live `crg-debug-haiku` skill was
restored to pristine (backup `.crg-eval-haiku/SKILL.md.bak.manual-abtest`).

**Why the "no RED, no edit" gate didn't bind.** Cell-3 timsort made a *different, worse* wrong edit
than cell 2 — it deleted the merge-direction heuristic entirely (`if (p[n-1].len < p[n+1].len) --n;`
→ unconditional `--n;`) — while still never building CPython, still testing the unbuilt system
interpreter, still reporting green, and emitting `DEBUG_COMPLETE` on try 2. There is no *suspected*
classification, no recorded RED, no `configure`/`make` anywhere in the logs. **Haiku read the hard
gate as advisory prose and edited anyway.**

**The real lesson.** A prose gate cannot force a weak model to build before it tests. Stopping the
timsort regression needs an *enforcement mechanism the harness owns* — the loop refusing to accept a
diff to compiled source unless a build + genuinely-failing-test artifact exists — not more SKILL.md
text. Prompt-only edits are the wrong lever for this failure mode on this model tier.

### Pattern preserved — "no RED, no edit" + trace-and-reverify (model-tier-gated, not discarded)

The edit was rejected *for haiku*, but the pattern itself is sound and worth keeping. It encodes a
real anti-pattern (a test that is green before the fix, or that runs against a stand-in/unbuilt
artifact, manufactures false confidence) and a real correction (build the artifact you edited; see a
genuine RED before touching code; mark *suspected* otherwise). What this round actually measured is
**not** "the pattern is wrong" — it is "prose alone does not bind a weak model to it."

Two reasons it stays on the table:

* **It is a prompt-compliance test, and compliance scales with model strength.** Haiku ignored the
  hard gate; Sonnet and Opus are far likelier to honor "build before you test / no RED, no edit."
  The same three edits should be re-run on the `crg-debug-sonnet` and `crg-debug` (opus/default)
  legs before the pattern is judged on its merits — a fail on the weakest tier is not a fail on all.
* **It is the spec for the harness-side gate.** Even where prose fails, the rule is exactly what an
  *enforced* loop would check: reject a diff to compiled source unless a build + genuinely-failing
  test artifact exists. The prose version is the human-readable form of the mechanism worth building.

Artifact preserved at `.crg-eval-haiku/SKILL.md.candidate-no-red-gate` (the full 187-line edited body:
trace-and-reverify + scratch-file rule + no-RED-no-edit gate) so the candidate survives outside the
scratchpad and can be dropped onto the sonnet/opus legs or fed to the harness-gate design verbatim.

### Diagnosis — why iterative-pristine timsort failed (recall 0.0 / precision 0.5)

Iteration alone did not help timsort, and the post-mortem is specific (read off `agent.diff`,
`report.md`, and both try logs):

* **It mislocalized the bug.** The planted bug is a missing OR-clause in the `merge_collapse`
  *while-condition* (the deeper-triple invariant `p[n-2] <= p[n-1] + p[n]`). The agent never touched
  the condition. It instead changed the tie-breaker *inside* the if-body, `p[n-1].len < p[n+1].len`
  → `p[n-1].len < p[n].len` — which is the **canonical-correct** CPython line. So it both **missed the
  real bug** (recall 0) and **turned correct code into a regression** (precision 0.5).
* **TDD in form, violated in substance.** It wrote `test_timsort.py`, but the test was inert three ways:
  (1) a tautological assertion (`sorted(x) != sorted(x)`, can never fail); (2) it exercised the
  **system Python's** `list.sort()` while the edit was in `Objects/listobject.c` — **CPython was never
  rebuilt**, so the test physically could not run the change; (3) its own report says `Tests: PASS → PASS`.
  The skill *already* said "test passes before fix → do NOT edit, mark suspected." The agent reported
  green-before-fix and edited anyway. The RED never happened.
* **Iteration made it worse, not better.** The try-2 resumed nudge asked it to trace a concrete input.
  It did — and used the trace to *confirm its already-made wrong edit*, then emitted `DEBUG_COMPLETE`.
  With no built binary, the hand-trace had no ground truth to contradict it, so the second pass became
  a rationalization engine. Self-declared-done let a confidently-wrong agent stop.

**Finding.** On cases the agent will not build, "write a test" without "and make it genuinely fail
first" is an *anti-signal* — a green-against-the-wrong-binary test manufactures false confidence and is
worse than no test. And once a wrong edit exists, an iterate-and-self-trace loop without a real oracle
reinforces it rather than correcting it.

**Enforcement (folded into cell 3's edited prompt).** The TDD gate is hardened to **"no RED, no edit"**:
the agent must see and record a real failing test before editing; a test that runs against a
*pre-built or system-installed* binary while the edit is to compiled source is **not** a RED — build
from the edited source, or you have no RED → do not edit, mark *suspected*. Hand-tracing is a
localization aid, never a substitute for RED. Cell 3 now tests whether this gate stops the timsort
regression (expected: timsort either reaches a real fix via a build, or correctly self-classifies as
*suspected* and makes **no** edit — both beat the confident regression).

## Round 4 — Workflow harness: enforcement in code, not prose

### Why this round

Rounds 2 and 3 converged on a single conclusion the prose could not escape: a `SKILL.md` gate
cannot bind a weak model. The "no RED, no edit" gate, hardened into the cell-3 prompt, was read by
haiku as advisory — it edited compiled source, tested an unbuilt interpreter, reported green, and
emitted `DEBUG_COMPLETE` anyway (Round 3 verdict). The doc named the fix in the same breath:
"Stopping the timsort regression needs an enforcement mechanism the harness owns ... not more
SKILL.md text," and "It is the spec for the harness-side gate." Round 4 builds that mechanism. The
crg-debug methodology is re-implemented as a **Workflow** — deterministic JavaScript that owns the
control flow — and the defining test for every gate becomes literal: *can the model skip it?* If a
gate is a function the script calls and an exit code the script reads, the answer is no.

### What was built

`.claude/workflows/crg-debug.js` runs five phases: Graph → Map → Discover → Verify → Fix. The
enforcement split is the whole point:

* **Script owns (deterministic, unskippable):** phase sequencing, concern partitioning, code-side
  dedup by `(file, rootCause)`, file-disjoint wave packing, loop termination (fixed-point + thrash +
  max-wave), survivor selection from verdicts, and ledger assembly.
* **Agents own (judgment + unavoidable I/O):** CRG graph queries, toolchain discovery, the baseline
  build, parallel discovery, adversarial verify, and the TDD fixes. They run shell and git because
  the Workflow script cannot.

The crux is the **per-bug close gate**. A fix agent applies its TDD fix and reports the narrowest
`testCommand` that exercises only its bug. A separate `bugGateAgent` then re-runs exactly that
command and reports the raw exit code; the script reads the exit code and decides closed-or-not. The
model never declares "passed" — its green claim is advisory, the exit code is authoritative. This is
the Round 3 "spec for the harness-side gate" made real. It also cured an earlier whole-suite gate
that deadlocked at 0 of 14 closed under per-file wave packing (one unfixed sibling failed the whole
suite and blocked every genuine fix); a bug now closes on its own test, so siblings cannot block it.

### SKILL → Workflow as a /command

The prose skill is not deleted so much as demoted from harness to reference, and the slash command
is rewired to launch the Workflow.

* **`SKILL.md` is now a ~45-line dispatcher**, down from a 177-line prose harness. It parses
  `$ARGUMENTS` into the Workflow's args and calls `Workflow({name:'crg-debug', args})`. The grammar:
  `repoRoot` is an explicit path or `--repo` flag, else the cwd when it is a git repo, else it stops
  and asks (no guessing across the multi-repo BLACKBOX/dawson workspace); `scope` is any non-flag
  focus text; `--model` selects the driver; `fix` defaults to **true** (full detect + TDD fix waves)
  with `--detect-only` opting out to a read-only ledger. A skill whose instructions tell the agent to
  call Workflow is one of the Workflow tool's sanctioned opt-in paths, so the dispatch is clean.
* **`methodology.md` (new, same directory)** holds the full methodology verbatim — the bug-class
  checklist, the real-vs-intentional rule, the fail-safe-defaults lens, the TDD discipline, the
  toolchain-discovery rules. It is reframed as a reference doc, not a runnable skill, because the JS
  now owns the enforcement the prose used to beg for.
* **Two consumers were repointed** at `methodology.md`: the Workflow itself (`crg-debug.js:35`,
  `const SKILL`, which each agent prompt cites by absolute path) and the `crg-debugger` subagent
  (`crg-debugger.md:12`). The anti-skip preamble and the Phase 0 to 5 orchestration prose simply
  deleted from the dispatcher, because they describe control flow the script now performs.

The architectural contrast is the thesis in one table:

| | `/crg-debug` skill (before) | `crg-debug` Workflow (after) |
|---|---|---|
| Enforcement | prose the model is trusted not to skip | gates the script owns as exit codes |
| Gate example | "no RED, no edit" (read as advisory) | `bugGateAgent` exit code the script reads |
| Model selection | none built in | uniform `model` arg applied to every agent |

### BugFix validation (haiku driver), three runs

The Workflow was run on BugFix with `model:'haiku', fix:true` and a full sweep — the same weak tier
the prose rounds used, so a gap here is a harness property, not a model upgrade.

| | Run 1 (README tells) | Run 2 (cleaned, old loop) | Run 3 (cleaned, fixed loop) |
|---|---|---|---|
| Confirmed | 11 | 14 | 13 |
| Deferred "intentional" | 4 | 0 | 0 |
| Fixed | 10 / 11, GREEN gate | 8 / 14, RED gate | 0 unfixed, GREEN gate |

**Read the metric difference first.** The skill legs elsewhere in this doc are graded by a
diff-vs-answer LLM judge into recall and precision. The Workflow produces a real run result instead:
a confirmed/deferred ledger plus an actual regression gate (`gcc -c` over all five C files and
`pytest`, real exit codes the script reads). A green gate proves the code compiles and the tests
pass, a strictly stronger signal than diff overlap with a reference answer. These numbers are
therefore self-contained; they do **not** map onto, and must not overwrite, the skill-leg BugFix
recall (haiku 0.79) in the Results tables above. Different harness, different measurement.

### Finding A — repo framing is a verify-phase confound

Run 1 deferred four real bugs (`add_numbers`, `fibonacci`, `factorial`, `calculate_average`, all in
`bug.py`) as "intentional." The cause was the corpus repo's own framing: a README announcing
"intentionally introduced bugs ... practice debugging" and `# Buggy <fn>` comments on every defect.
The adversarial verifiers read those tells and classified genuine contract violations as deliberate
design, exactly the trap the real-vs-intentional lens is supposed to avoid. Neutralizing the framing
(rewrote the README as a real algorithms library, "algokit"; replaced every `# Buggy` comment with
one stating the true contract; kept every buggy line at its original line number; committed as
`d24d4b4`) dropped deferred from 4 to 0 and raised confirmed from 11 to 14, with a 0% false-positive
rate throughout. This was never false positives; it was a classifier reading the repo's marketing.
The implication is twofold: teaching-framed corpus repos bias the intentional classifier and should
be neutralized before they are trusted as ground truth, and the sensitivity is model-tier dependent
(haiku reads the tells; stronger tiers are likelier to weigh the contract over the comment), which is
the standing "prompt gates scale with model" lesson surfacing in the discover/verify phase rather
than in the fix phase.

### Finding B — a latent harness bug the cleanup exposed

Removing the misclassification was correct, and it immediately broke the fix loop: Run 2 closed only
8 of 14 with a RED gate, worse than Run 1's prose-era 10 of 11. The cleanup did not cause the
regression, it revealed one. With the four formerly-deferred bugs back in the queue, `bug.py` now
held seven bugs in a single file, and the fix loop could not drain it. Two defects, confirmed by
reading the loop:

1. **File-disjoint wave packing serialized one fix per file per wave.** One agent exclusively owns a
   file per wave, so `bug.py` could receive at most one fix each wave while its other six bugs waited.
2. **The thrash guard conflated deferral with thrashing.** Bugs deferred only because their file was
   busy this wave were added to `seenKeys`, so when they legitimately reappeared next wave the guard
   fired "re-queued a previously seen (file, root-cause), needs human" and aborted the loop. Run 1 was
   green only because four of `bug.py`'s bugs were hidden as intentional, thinning the file enough to
   drain in the available waves.

The fix restructures the fix phase (`node --check` clean):

* One agent now owns **all** of a file's bugs via a per-bug `fixes[]` schema, draining a dense file in
  one wave instead of serializing it.
* A per-agent cap, `MAX_BUGS_PER_FIX = 4`, sends a denser file's extra bugs to later waves as
  deferred chunks (an agent owning a dozen bugs would overload its context and tank the fix rate).
* The thrash guard counts **only genuinely-failed retries** (`requeued`), never deferred chunks, so
  normal file-contention deferral can no longer abort the loop.
* The closing evaluation is scoped to the bugs actually **attempted** this wave, which removed a
  double-count (`fixed:15` against `confirmed:13`) and a latent false "RED not observed" that arose
  when a file-owning agent fixed a deferred sibling and the next wave re-attempted an already-fixed bug.

Run 3 result: all bugs fixed, 0 unfixed, GREEN gate, drained in two waves (six files in wave 1, then
`bug.py`'s deferred chunk in wave 2).

### What Round 4 settles, and what it does not

It settles the question the prose rounds kept losing. Where haiku read "no RED, no edit" as advisory
and shipped a confidently-wrong timsort fix (Round 3), the Workflow's per-bug gate is an exit code the
script acts on, unskippable by construction. The enforcement mechanism the doc specified now exists
and works on the weak tier it was specified for. The honest caveats stand: this is one repo, n=1, on
haiku, against the easy corpus. The standing limitations — N repeats per cell to separate signal from
stochasticity, and harder targets to break the recall ceiling — are unchanged, and the Tier-1 hard
cases (timsort, asyncio, sudo) have not yet been run through the Workflow. Round 4 proves the gate
binds; it does not yet prove the Workflow ceilings the discriminator set. That is the next run.

## Status (update as runs land)

* opus: baseline complete (1.00 / 1.00). synth candidate recovered. improved not run (ceiling; decision open).
* sonnet: baseline complete (1.00 / 0.966). synth + improved complete; candidate reverted (no lift).
* haiku: full `all` complete. honest baseline 0.729 / 0.80 (five cells, 5th recovered after harness
  bug 4 fix), improved 0.929 / 1.00, candidate kept (+0.199 / +0.20). This is the only leg with a
  real recall lift, because it is the only model weak enough to leave misses for the loop to learn from.
* **Tier-1 hard cases: in progress.** Three real upstream bugs (timsort, asyncio Condition, sudo
  CVE-2021-3156) wired into all three legs as cells 6-8. Sonnet and haiku baselines running per case
  via `--only`; opus not yet run. First landed cell: haiku timsort 0.00 / 0.00 (missed the invariant).
* **Round 4 (Workflow harness): built and validated on BugFix-haiku.** crg-debug re-implemented as
  `.claude/workflows/crg-debug.js`; `/crg-debug` now dispatches to the Workflow (`SKILL.md` is a thin
  dispatcher, `methodology.md` is the shared reference both the Workflow and the `crg-debugger` agent
  read). BugFix-haiku reaches 0 unfixed with a green regression gate after a README-confound fix
  (deferred 4 → 0) and a wave-packing / thrash-guard fix (8/14 → all fixed). Tier-1 hard cases not yet
  run through the Workflow.

## Reproduce

```bash
cd /Users/lechristopherblackwell/BLACKBOX/dawson
bash .crg-eval/run.sh all                 # opus
bash .crg-eval-sonnet/run-sonnet.sh all   # sonnet
bash .crg-eval-haiku/run-haiku.sh all     # haiku
# per-leg knobs: CRG_EVAL_DEBUG_MODEL / SYNTH_MODEL / JUDGE_MODEL / CONCURRENCY, and --only REPO, --dry-run
```

Round 4 Workflow (run inside a Claude Code session, not the shell harness):

```
Workflow({name:'crg-debug', args:{repoRoot:'/Users/lechristopherblackwell/BLACKBOX/dawson/BugFix', scope:'', fix:true, model:'haiku'}})
```

or the `/crg-debug <repo> [--detect-only] [--model haiku]` command, which dispatches to the same
Workflow via the `SKILL.md` dispatcher.

Cleanup when done: `git -C dawson/<repo> worktree remove <leg-dir>/repos/<repo>` per repo,
and optionally remove the `crg-debug-sonnet` / `crg-debug-haiku` global skills.
