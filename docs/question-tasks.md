# Question tasks

A question task asks an agent a question with a known answer and grades what it says. There
is no repository and no diff. Use it for retrieval, lookup and classification skills.

[Back to the README](../README.md)

## Contents

- [Try it offline](#try-it-offline)
- [The pieces](#the-pieces)
- [The question file](#the-question-file)
- [How a question is graded](#how-a-question-is-graded)
- [The numbers](#the-numbers)
- [Repeated trials](#repeated-trials)
- [Measured or canned](#measured-or-canned)
- [Hard stops](#hard-stops)

## Try it offline

```bash
uv run proofbench run --unchecked --config examples/question-demo/proofbench.question.yaml
```

This uses a stub arm that needs no model, so it costs nothing. Three questions, one of them
unanswerable. Expect `accuracy: 0.667`.

## The pieces

| Piece | What it is | Where it is described |
|---|---|---|
| Question file | JSONL, one question per line, with its answer | [The question file](#the-question-file) |
| Arm | Your executable. It gets one question and prints one answer | [The question arm](io-contracts.md#the-question-arm) |
| Judge prompt | Your rubric for answers the ids cannot settle | [Prompts](configuration.md#prompts) |
| Config | Ties them together | [Configuration](configuration.md) |

A minimal config:

```yaml
runner: arms/my-arm.sh      # any executable
models: [sonnet]            # passed to the arm as --model
judge_model: opus
judge: judge.md             # your own rubric; leave it out to grade by exact id alone
corpus:
  - kind: question
    file: questions/lineage.jsonl
```

## The question file

One JSON object per line.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | text | yes | Unique across the whole corpus |
| `text` | text | yes | The question. This and `id` are all the arm sees |
| `answer` | list | yes | The ids of the correct answer. Empty when there is none |
| `answerable` | true or false | yes | False when the correct response is to decline |
| `answer_names` | list | no | The answer in words. Shown to the judge |
| `class` | text | no | The answer class the [coverage gate](building-an-eval.md#the-gates) counts |
| anything else | | no | Kept in the records. Never shown to the arm |

Example:

```json
{"id": "LQ-0002", "text": "Who supervised Mikko Korhonen?", "answer": ["lutpub:Kalviainen, Heikki"], "answer_names": ["Heikki Kalviainen"], "answerable": true}
```

The file is checked before any arm is asked. A bad line is reported by its line number.

## How a question is graded

Three rules, tried in order. The first that applies decides.

1. **Abstention.** If the arm declined, or the question is unanswerable, the grade is correct
   only when both are true: the arm declined an unanswerable question.
2. **Exact match.** If the arm's `answer_ids` are the same set as the question's `answer`, the
   grade is correct. No model is involved.
3. **The judge.** Otherwise the judge reads the arm's answer and returns 1 or 0.

A config with no `judge` key stops after rule 2: ids that do not match are graded wrong and
no model is asked. Use it when the system answers with an id from a fixed list, such as a
label. Use a judge when a right answer can come in words.

Details:

- Ids are compared ignoring case, extra spaces and Unicode form. Accents and punctuation are
  kept, so two different names stay different.
- The judge must return exactly 1 or 0. A fraction stops the run, because the scoreboard
  counts that field as correct answers.
- Each record says which rule decided it, in `graded_by`. A record the judge decided also
  says what that call cost, in `judge_cost_usd`.

## The numbers

| Number | What it tells you |
|---|---|
| `accuracy` | Share of attempts graded correct. A correct refusal counts as correct |
| `tokens_per_correct` | Tokens spent for each correct attempt. Lower is better |
| `non_abstention_rate_answerable` | When an answer existed, how often the arm tried |
| `abstention_correct_unanswerable` | When no answer existed, how often the arm declined |
| `pass^k`, `pass@k` | How consistent the arm is over repeated trials |
| `unstable_questions` | Questions answered both right and wrong |

Two rules keep the names honest:

- **A corpus with nothing answerable gets no key named `accuracy`.** It reports
  `abstention_rate` and `tokens_per_correct_abstention` instead. Otherwise an arm that refuses
  everything would look perfect.
- **Nothing correct means no price, not a price of zero.** `tokens_per_correct` is then null.
  A zero would rank the worst arm as the cheapest.

`answerable` and `unanswerable` are printed on every leg, so you can always check what a rate
was measured over.

## Repeated trials

One trial shows whether the arm can be right. It does not show whether it is right every time.

```yaml
trials: 3
objective: pass^3
```

Each question is then asked three times, each a fresh run of the arm.

- **`pass^k`**: the chance that k trials of one question are all correct. This is the
  reliability reading. Gate on it for anything people will rely on unattended.
- **`pass@k`**: the chance that at least one of k trials is correct. This is the capability
  reading.

How they are worked out:

- Both are averaged over the questions and reported for every k from 1 to `trials`.
- With c of n trials correct, a question adds `C(c,k)/C(n,k)` to `pass^k` and
  `1 - C(n-c,k)/C(n,k)` to `pass@k`.
- `pass^1` and `pass@1` both equal `accuracy`.
- The gap between `pass@k` and `pass^k` is the arm's inconsistency.

With trials:

- Each trial keeps its own files under `<model>/<question id>/trial-<n>/`.
- `questions`, `answerable` and `unanswerable` count questions. Token and cost totals cover
  every trial.

## Measured or canned

A leg's first lines say where its numbers came from.

- `stubbed: true` means a canned reply answered at least one question.
- `is_measured: true` is printed only when the arm said it was not canned **and** reported a
  cost above zero.
- An arm that says nothing is not counted as measured. Silence is not evidence.

The demo arm is canned, so its leg reads `is_measured: False`. That is the correct reading.

## Hard stops

Each of these stops the run:

- A question line that is not JSON, or lacks a required field.
- Two questions sharing an id.
- An arm that exits non-zero, prints no JSON object, or leaves out a required field.
- A judge verdict that is not 1 or 0.
- One leg answered by more than one model.
- An objective naming a k above `trials`.
