# The Gate the Model Could Not Skip

*A field journal from evaluating a debugging skill, and what it took to make the eval tell the truth.*

This is the story behind [CRG-EVAL-RESULTS.md](./CRG-EVAL-RESULTS.md). That document is the
clinical record: tables, exact numbers, per round verdicts. This one is the journey. The wrong
turns, the moments a confident number turned out to be a lie, and the slow realization that no
amount of prompt wording would make a weak model rigorous. If you want the evidence, read the
results doc. If you want to know how I got there, stay here.

A note on two terms. **CRG** is code-review-graph, a knowledge graph of a codebase that an agent
can query to localize code. **crg-debug** is a skill that drives a graph aware debugging sweep:
map the hotspots, fan out parallel discovery over disjoint concerns, verify findings adversarially,
then fix in TDD waves. The whole project below is one long attempt to find out whether that skill
actually works, and then to make it work on a model weak enough to embarrass it.

## The premise

A debugging skill is only as trustworthy as the proof that it works. Anyone can write a prompt
that *sounds* like a methodology. The only honest way to know is to plant bugs you already have the
answers to, run the skill, and grade what it changed against the known fix.

So that is what I built: an eval over five debugging-interview repos, each with a ground-truth
gold branch. Grade each fix with an LLM judge that compares the agent's diff to the reference
diff and reports recall (did it fix the planted bugs) and precision (did it avoid breaking things).
Then run the exact same harness on three driver models, opus and sonnet and haiku, to answer the
question that actually matters: does the *method* carry the result, or just the model?

The honest goal was never "prove it works." It was "find where it breaks." That framing is the
only reason any of the rest happened.

## First, the measuring stick lied to me

Before the models could fail, the harness failed, and it failed in the most dangerous way a
measurement system can: quietly.

There were four bugs, all of them classic `set -euo pipefail` landmines, and all of them masked by
whether a given run happened to have a terminal attached. A JSON extractor that choked on a model's
prose preamble. A helper that returned 1 when piped because its last line was a conditional. A
watcher that latched onto the wrong process and declared a finished run dead. Annoying, fixable,
the usual.

Then there was the fourth one, which changed how I thought about the whole exercise.

On the haiku leg, one cell scaffolded a test harness, ran `npm install`, and the capture step swept
the entire `node_modules` tree into the diff. The result was a 442,828 line diff. The judge prompt
that embedded it was 22.8 MB. The judge was invoked with the whole prompt as a single shell
argument, which sailed straight past `ARG_MAX`, so the call failed. But the call was guarded by
`|| true`. So the empty output flowed onward. The extractor emitted nothing, `jq` exited 0, the
"or die" guard never fired, an empty grade was written, and the aggregator simply skipped the empty
file.

The scoreboard then reported a confident `macro_recall=0.662`, as if complete. It was secretly an
average of four cells, not five.

That is the worst possible failure. Not a crash, not a stack trace, just a clean wrong number with
no reason to distrust it. I only caught it because the recovered fifth cell scored 1.00 and dragged
the honest baseline to 0.729, materially different from the lie. The fix was to make every empty or
non-numeric grade a hard stop, route big prompts through stdin instead of argv, and exclude
installed dependencies from the capture.

> **An eval that fails open does not just miss data. It manufactures false confidence.** A
> measurement system must fail loud, or it will hand you a wrong number you have every reason to
> believe.

I keep coming back to that one. It is the seed of everything Round 4 eventually became.

## The ceiling problem

With an honest harness, a new problem appeared, and it was almost funny: the strong models were
too good.

Opus scored a flawless 1.00 / 1.00. Sonnet sat right next to it. On these repos the frontier models
miss almost nothing, which sounds like success until you remember the point of the exercise. I had
built a closed improvement loop, where the grades feed a synthesis step that proposes edits to the
skill, and an improved run re-measures. A loop like that learns from misses. When nothing misses,
there is nothing to learn.

The counterintuitive turn took me a while to accept. **The weak model is not the liability in this
setup. It is the only source of signal.** Haiku's misses are the curriculum. A leg that scores 0.729
is worth more to a self-improving loop than a leg that scores 1.00, because only the imperfect one
tells you where the method is thin. From that point on, haiku was the protagonist.

## Harder targets

If haiku's misses are the curriculum, the easy repos are too forgiving a syllabus. Even haiku
ceilinged on most of them. So I went looking for bugs that would actually hurt.

The Tier-1 hard cases are real production bugs from CPython and sudo: the timsort `merge_collapse`
run-stack invariant that sat latent in CPython and Java and Android for years until formal
verification found it, the asyncio `Condition.notify` lost-wakeup race, and the sudo Baron Samedit
heap overflow (CVE-2021-3156). The selection rule was deliberate. Famous CVEs like Heartbleed are
useless here, because a frontier model recognizes them on sight and you end up measuring training
recall, not debugging. These three are the opposite: one subtle line buried in a real source file,
surrounded by production-grade code that gives no hint, where the correct reasoning is about an
invariant or a race rather than a typo.

And the discriminator worked on the very first interesting cell. On timsort, sonnet scored 1.00,
and haiku scored 0.00. A clean separation the easy repos never produced. Haiku's localization was
perfect: it found the file, the function, the exact `if` block. Then it edited the wrong line inside
the right block, rewriting correct tie-break logic into incorrect logic while never touching the
actual invariant check one level up. Recall 0 because it missed the bug, precision 0 because its one
edit introduced a new defect. It scored worse than an empty diff would have, by confidently shipping
a wrong fix.

That failure was not a disappointment. It was the prize specimen. A real, repeatable, well
understood miss on a strong-ish driver, which is exactly what the easy repos could never generate.
Now I had something to fix.

## The conundrum that defined the project

Here is where I spent the most time and learned the most, mostly by being wrong.

The obvious move, when a model misdiagnoses a bug, is to write a better prompt. Tell it what it did
wrong. Add a rule. So I did, over and over, and the eval kept teaching me the same lesson in
increasingly expensive ways.

**The A/B that backfired.** I hand-authored two evidence-cited edits into haiku's skill: a gate that
said confirm the cause line or revert, plus a rule against leaving scratch files. The result was a
clean negative. Precision rose on every case. Recall *fell* on the two cases haiku had previously
passed. The shape of the failure was the lesson: a caution-shaped edit makes an already-timid model
edit less and revert more, and on a weak model less editing converts directly into lost recall. The
intervention aimed at a precision problem and made the recall problem worse.

**Round 2, the trace-and-reverify scaffold.** I replaced the confirm-or-revert gate with something
that tried to supply reasoning instead of caution: name the invariant, build a concrete input that
violates it, hand-execute to the line where it first breaks, re-verify, then look for a second
violating input. Better in theory. But on the C cases the re-verify step is hand-simulation, and a
weak model can hand-simulate incorrectly with total confidence.

**Round 3, just let the session continue.** A real user does not take a one-shot suggestion and
stop. They keep the chat open and often crack on the third pass what they missed on the first. So I
made the harness resume the same session across up to three tries with a neutral nudge. This is the
one that taught me the most, because iteration without a real oracle did not help. It became a
*rationalization engine*. On timsort, the agent used its second pass to hand-trace its own already
wrong edit, used the trace to confirm it, and emitted `DEBUG_COMPLETE`. With no built binary to
contradict it, more thinking just entrenched the mistake.

And underneath all of it sat the gate I was proudest of and that failed hardest. I hardened the TDD
rule into "no RED, no edit": you must see a real failing test before you touch code, and a test that
runs against an unbuilt interpreter does not count. Haiku read it as advisory. It edited compiled
source, tested the system Python instead of the source it changed, reported green, and emitted
`DEBUG_COMPLETE` anyway. No build, no RED, no hesitation.

> **You cannot wordsmith a weak model into rigor.** A prose gate is a request. Compliance with a
> request scales with the strength of the model reading it, which means the exact model that most
> needs the gate is the one most likely to ignore it.

## The realization

The thing about a good eval is that it writes its own conclusions, and then you have to be honest
enough to read them.

The results doc had already said it, twice, in plain language. After the Round 3 failure it
concluded that stopping the timsort regression "needs an enforcement mechanism the harness owns,
not more SKILL.md text." And in the same breath it noted that the rejected prose gate was still
valuable, because "it is the spec for the harness-side gate."

I had been treating those sentences as a postmortem. They were a design brief. The fix was never
going to be words. It was going to be code that does not ask.

## Round 4, the turn

So I re-implemented crg-debug as a Workflow: deterministic JavaScript that owns the control flow,
with agents reduced to what only they can do. The script owns phase sequencing, concern
partitioning, dedup, wave packing, loop termination, and the ledger. The agents own judgment and the
I/O the script cannot perform: graph queries, toolchain discovery, the baseline build, discovery,
adversarial verify, and the actual fixes.

The defining test for every gate became literal. Not "is this rule clear" but "can the model skip
it?" If a gate is a sentence in a prompt, the answer is yes. If a gate is a function the script calls
and an exit code the script reads, the answer is no.

The crux is the per-bug close gate. A fix agent applies its fix and reports the narrowest
`testCommand` that exercises only its bug. A separate agent then re-runs exactly that command and
reports the raw exit code. The script reads the exit code and decides closed or not closed. The model
never declares "passed." Its green claim is advisory; the exit code is authoritative.

> **A claim you cannot make is a claim you cannot fake.** The Round 3 gate failed because "passed"
> was a thing the model could say. The Round 4 gate works because "passed" is a thing only the shell
> can return.

This also cured an earlier deadlock I had hit with a whole-suite gate, where one unfixed sibling
failed the entire suite and blocked every genuine fix, stalling at 0 of 14 closed. Once a bug closes
on its own narrow test, siblings cannot hold it hostage.

## The refactor that made it a command

Demoting the prose was the satisfying part. `SKILL.md` went from a 177 line harness, all
orchestration and anti-skip pleading, to a roughly 45 line dispatcher whose only job is to parse
arguments and call `Workflow({name:'crg-debug', args})`. The judgment prose that still mattered, the
bug-class checklist, the real-versus-intentional rule, the fail-safe-defaults lens, moved into a new
`methodology.md` reference that both the Workflow and the standalone debugger agent read. The
control-flow prose simply deleted, because the JavaScript now performs what it used to describe.

The whole thesis fits in one contrast. The skill was prose I was trusted not to skip. The Workflow
is gates the script owns. As a bonus, the dispatcher gained a uniform `model` argument applied to
every agent, something the prose skill never had.

## The two surprises in validation

I validated on the BugFix repo with haiku as the driver, the same weak tier the prose rounds used,
so any gap would be a property of the harness and not a model upgrade. It took three runs and two
genuine surprises to get to green.

**Finding A: the repo was lying to the classifier.** Run 1 deferred four real bugs as "intentional."
The cause was the corpus repo's own framing. Its README announced "intentionally introduced bugs
for practice," and every defect carried a `# Buggy` comment. The adversarial verifier read those
tells and classified real contract violations as deliberate design, which is exactly the trap the
real-versus-intentional lens is meant to avoid. I rewrote the README as a real library, replaced the
comments with statements of the true contract, and kept every buggy line at its original position.
Deferred dropped from 4 to 0. The classifier had been reading the repo's marketing, and that
sensitivity is itself model-tier dependent: haiku reads the tells, stronger models weigh the contract
over the comment.

**Finding B: fixing the first surprise exposed a latent bug.** With the four bugs back in the queue,
`bug.py` now held seven bugs in one file, and Run 2 closed only 8 of 14 with a red gate, worse than
Run 1. The cleanup had not caused a regression. It had revealed one. Reading the loop, the cause was
two compounding defects. File-disjoint wave packing let one agent own a file per wave, so a dense
file could receive at most one fix per wave while its other bugs waited. And the thrash guard,
meant to detect genuine failed retries, had been adding bugs deferred merely because their file was
busy to the same "seen" set, then aborting the loop when they legitimately reappeared. Run 1 had only
looked green because four of `bug.py`'s bugs were hidden as intentional, thinning the file enough to
drain in time.

The fix restructured the fix phase: one agent now owns all of a file's bugs at once, a per-agent cap
sends a denser file's overflow to later waves as deferred chunks, and the thrash guard counts only
genuinely failed retries, never deferral. Run 3 closed everything. Zero unfixed, green gate, drained
in two waves.

It is worth sitting with the chain there. A misclassification born from a README masked a wave-packing
bug, which was masked again by a thrash guard that could not tell deferral from thrashing. Three
layers, each hiding the next, and only an honest run with all the bugs surfaced forced them out. The
same lesson as harness bug four, wearing different clothes: things that fail quietly compound.

## What I actually learned

Pulling the threads together, the journey reduces to a handful of things I now believe more firmly
than when I started.

**Fail loud or do not measure.** The most dangerous output of a test harness is a confident wrong
number. If a path can swallow an error and emit a plausible result, it eventually will, and you will
trust it.

**The weak model is the signal, not the noise.** A self-improving loop learns from misses. Frontier
models on easy repos do not miss, so they teach nothing. Deliberately running the model that fails
is how you find what the method is missing.

**Prompt compliance scales with model strength, so a prose gate is a request and not a guarantee.**
The model that most needs a rule is the one most likely to read it as optional. This is the single
most useful thing the whole eval surfaced, and it generalizes well beyond debugging.

**When a rule must hold, move it into code the model cannot route around.** The difference between
Round 3 and Round 4 is the difference between asking the model to verify and letting only the shell
report the verdict. Enforcement belongs wherever the model cannot reach.

And the honest caveats, because the eval would not forgive me for omitting them. Round 4 is still
n=1, on one easy repo, with haiku. It proves the gate binds. It does not yet prove the Workflow
ceilings the hard cases. The Tier-1 set, timsort and asyncio and sudo, has not yet run through the
Workflow. That is the next run, and the standing limitations, N repeats per cell to separate signal
from stochasticity and harder targets to break the recall ceiling, are unchanged.

The through-line is almost embarrassing in hindsight. The eval kept telling me the answer in its own
conclusions, round after round. I just had to stop trying to say it in a prompt and start building it
in code.

---

*For the numbers behind every claim here, see [CRG-EVAL-RESULTS.md](./CRG-EVAL-RESULTS.md): the
harness bugs in "Harness bugs found and fixed," the ceiling in "Findings," the hard cases in "Tier-1
hard cases," the prose-gate failures in Rounds 2 and 3, and the Workflow turn in Round 4.*
