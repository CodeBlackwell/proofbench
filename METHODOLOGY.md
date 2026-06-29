# Methodology

proofbench is the distilled form of a long evaluation of one debugging skill. The full field
journal is [docs/crg-eval-journey.md](docs/crg-eval-journey.md), with the numbers in
[docs/crg-eval-results.md](docs/crg-eval-results.md). This page is the part that generalizes:
the handful of things that evaluation taught, each now a property the harness enforces rather
than advice you have to remember.

## 1. Fail loud, or do not measure

The most dangerous output of a test harness is a confident wrong number. In the original run, a
judge call silently exceeded the OS argument limit, its error was swallowed, an empty grade
flowed onward, and the scoreboard reported a clean average of four cells while presenting it as
five. Not a crash. A plausible lie.

proofbench makes that failure impossible to ignore. Every empty or non-numeric grade raises and
halts. Large prompts go to the judge on stdin, never on argv, so an embedded diff cannot abort
the call past the argument limit. Capture excludes installed dependency and cache trees, which
are never the agent's work and can balloon a prompt past that limit. These live in `util.py`,
`judge.py`, and `capture.py`, and they are the subject of the test suite, because they are the
product.

## 2. The weak model is the signal, not the noise

A self-improving loop learns from misses. Frontier models on easy tasks miss almost nothing, so
they teach nothing. The counterintuitive consequence: the weak model is not the liability in
this setup, it is the only source of signal. Its misses are the curriculum.

So proofbench is model-sweep native. `models:` is a list, and `optimize` drives the **weakest**
leg on purpose. To keep the signal clean, `judge_model` and `synth_model` are held constant and
default to a strong model. You never let the model under test grade its own homework or rewrite
its own instructions.

## 3. A prose gate is a request, not a guarantee

The longest stretch of the original work was spent trying to fix a weak model's misdiagnoses by
writing better instructions. It failed, repeatedly and expensively, and always the same way.
Prompt compliance scales with model strength, which means the exact model that most needs a rule
is the one most likely to read it as optional. You cannot wordsmith a weak model into rigor.

The lesson for any eval is narrower and sharper: when a rule must hold, it belongs in code the
model cannot route around, not in text the model is trusted not to skip. proofbench applies this
to its own gates. The keep/revert decision in `optimize.py` is the harness comparing two numbers.
"The score held" is not a thing the model can say. It is a thing only the comparison can return.

## 4. The corpus is part of the method

Two findings about the data, not the harness, generalize into [CORPUS.md](CORPUS.md):

- **Do not use famous bugs.** A frontier model recognizes Heartbleed on sight, and then you are
  measuring training recall, not method. Pick subtle, real defects where the correct reasoning is
  about an invariant or a contract, not a typo a model has memorized.
- **Do not let the corpus telegraph its answers.** In one run the task repos announced their own
  planted bugs in the README and in `# Buggy` comments. The judge read the marketing and
  classified real contract violations as intentional design. A task that advertises its answer
  measures nothing. State the true contract; never label the defect.

## The arc, in one line

The evaluation kept writing its own conclusions, round after round, and the work was learning to
stop saying them in a prompt and start building them in code. proofbench is what that looks like
when it is finished: the lessons are the implementation.
