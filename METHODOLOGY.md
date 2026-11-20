# Methodology

Why proofbench is built the way it is. It came out of a long evaluation of one debugging
skill, and each lesson from that evaluation is now something the tool enforces, not advice
you have to remember.

- The story of that evaluation: [docs/crg-eval-journey.md](docs/crg-eval-journey.md)
- Its numbers: [docs/crg-eval-results.md](docs/crg-eval-results.md)

[Back to the README](README.md)

## Contents

- [1. Fail loud or do not measure](#1-fail-loud-or-do-not-measure)
- [2. The weak model is the signal](#2-the-weak-model-is-the-signal)
- [3. A rule in a prompt is a request](#3-a-rule-in-a-prompt-is-a-request)
- [4. The corpus is part of the method](#4-the-corpus-is-part-of-the-method)
- [5. The thing being measured must not see the answer](#5-the-thing-being-measured-must-not-see-the-answer)
- [The arc in one line](#the-arc-in-one-line)

## 1. Fail loud or do not measure

**What happened.** The most dangerous output of a test harness is a confident wrong number.
In the original run:

- A judge call silently exceeded the operating system's argument limit.
- Its error was swallowed, and an empty grade flowed onward.
- The scoreboard reported a clean average of four cells and presented it as five.

It was not a crash. It was a plausible lie.

**What proofbench does.**

- Every empty or non-numeric grade stops the run.
- Large prompts go to the judge on stdin, never as an argument, so a long diff cannot abort
  the call.
- Dependency and cache folders are left out of the captured diff. They are never the agent's
  work and can make a prompt enormous.
- Every git command and every child process is checked. A failure stops the run in one line.
- The config and the question file are checked whole before anything is paid for.

**The same rule in question tasks.** Each of these was a decision worth writing down:

- **A missing token count is fatal.** Without `tokens_in` and `tokens_out` there is no tokens
  per correct answer, and a zero there would read as a free answer.
- **Nothing correct means no price, not a price of zero.** `tokens_per_correct` is undefined
  when nothing was correct. It is reported as null, and reading it as an objective stops the
  run. A zero would rank the worst arm as the cheapest.
- **The judge reads words, never ids.** An exact match on ids settles a question with no model
  involved. The judge is only reached for prose. Its verdict must be 1 or 0, because partial
  credit would quietly inflate accuracy.
- **A corpus with nothing answerable gets no key named accuracy.** Calling that number
  accuracy makes an arm that refused everything look perfect. Such a leg reports
  `abstention_rate` instead.
- **Measured is a positive claim.** A leg counts as a measurement only when the arm says it
  was not canned and says what it cost. Silence is not evidence.
- **The grid's axes come from the design, never from the data.** A table drawn over the cells
  that happen to be filled looks complete with two cells of fifteen. Every cell prints, and an
  empty one prints as empty.

## 2. The weak model is the signal

**What happened.** A loop that improves a skill learns from misses. Frontier models on easy
tasks miss almost nothing, so they teach nothing.

**The consequence.** The weak model is not the liability in this setup. It is the only source
of signal. Its misses are the curriculum.

**What proofbench does.**

- `models` is a list, so every run can sweep several models.
- `optimize` runs against the last entry, the weakest, on purpose.
- `judge_model` and `synth_model` are held constant. They default to the first entry, so list
  the strongest model first or name them yourself.
- The model under test never grades its own work or rewrites its own instructions.

## 3. A rule in a prompt is a request

**What happened.** The longest stretch of the original work went into fixing a weak model's
mistakes by writing better instructions. It failed, repeatedly and expensively, in the same
way every time.

- How well a model follows a prompt grows with how strong the model is.
- So the model that most needs a rule is the one most likely to treat it as optional.
- You cannot word a weak model into being rigorous.

**What proofbench does.** When a rule must hold, it lives in code the model cannot route
around.

- The keep or revert decision in `optimize` is the harness comparing two numbers.
- "The score held" is not something the model can say. Only the comparison can return it.
- A task can list its own ground-truth items. The judge then rules on each one, and the
  harness counts recall. The judge prompt already said what an item was; the judge still
  counted a rewritten README as an item on one task and set one aside on another.

## 4. The corpus is part of the method

Two findings about the data, not the harness. Both are expanded in [CORPUS.md](CORPUS.md).

- **Do not use famous bugs.** A frontier model recognises Heartbleed on sight, and then you
  are measuring memory, not method. Pick subtle, real defects where the reasoning is about an
  invariant or a contract.
- **Do not let the corpus point at its answers.** In one run the task repos announced their
  own planted bugs in the README and in `# Buggy` comments. The judge read the hints and
  classified real contract violations as intended design. State the true contract and never
  label the defect.

## 5. The thing being measured must not see the answer

**What happened.** A later audit found the harness itself leaking.

- A question arm was handed the whole question record, answer key included.
- A repo agent worked in the repository that held the answer branch, one `git checkout` away.
- The rewrite in `optimize` was scored on the same items whose answers it had been shown.

None of these needed a dishonest model. An arm that simply passed its input along, or an
agent that listed its branches, would have been graded against a key it had been given.

**What proofbench does.**

- An arm is handed a question's id and text, and nothing else.
- A repo agent works in a throwaway clone that holds the broken branch alone, with no remote.
- `optimize` learns from one part of the corpus and is scored on another, marked
  `holdout: true`.
- The judge runs with no tools and none of your personal configuration, so a diff cannot
  instruct it and a grade does not depend on where you ran the command.

## The arc in one line

The evaluation kept writing its own conclusions, round after round. The work was learning to
stop saying them in a prompt and start building them in code. proofbench is what that looks
like when it is finished: the lessons are the implementation.
