---
name: eval-docket
description: Work out with the owner of an agentic system, through a short multiple-choice survey, which claims about it an eval can honestly test — each with the ground its known answers stand on, what the system is shown, a grader, and a stated honesty condition — then write it down as an eval docket. Also puts an existing eval's ambiguous tasks, the ones with more than one defensible answer, to the owner for a ruling. Use before /proofbench, or when someone says "what should my eval measure", "what can I honestly test", "grill me about my eval", or "these tasks are ambiguous".
argument-hint: "[path to the target repo]"
user_invocable: true
---

# The eval docket

Produce **one markdown file**, `evals/docket.md` in the target repo. It names what the system
can honestly be tested on, what each test stands on, and what would make each score a lie.
`/proofbench` reads it as guidance. It is never a task list, and it passes no gate.

A repo shows how a system starts and what it returns. It cannot show that the labelled answers
record something the system is never shown, that a model wrote half the answer key, or that
two labels are one question asked twice. That knowledge is in the owner's head, and the only
way out of that head is to ask.

The skill has two passes. Say which one you are running.

- **The claims**, before an eval is built: what it should test at all.
- **The ambiguous tasks**, once an eval has tasks: the ones with more than one defensible
  answer.

**This skill spends nothing.** It reads, asks and writes. It runs no model on the system and
no `proofbench check`. Every paid step belongs to `/proofbench`.

## The eight things a repo cannot tell you

Everything you are asking for falls in here. Track which are still empty.

1. **The decision.** Who reads the score, and what they do differently when it moves. A claim
   with no decision behind it is curiosity.
2. **The unit, in their words.** What one task is, what the system is shown for it, and what
   it gives back. Every claim below inherits this.
3. **The ground.** Where the known answers come from: history they own (a merged fix, what
   happened next, a fixture), their own judgement, or a model. An answer a model wrote is not
   ground until they have approved that one answer.
4. **Reach.** Whether the answer can be reached from what the system is shown. An answer that
   records what happened after the run cannot be. This is the most expensive error there is:
   an eval nobody can pass costs a full run to discover.
5. **The classes, and their balance.** The kinds of right answer, which one is common enough
   that always saying it scores well, and whether declining to answer is ever right.
6. **The grader, and how it lies.** Whether a command can check the result, whether the answer
   is an id from a fixed list, or whether only a reader can judge it. Then the leaks: a task
   that names its own answer, an answer sitting in the history the system can read.
7. **The path.** Whether how the system gets there matters, which steps it must or must never
   take, and what its answer owes to what its tools returned.
8. **Dead ends, and the not yet harvested.** What has been measured and is saturated, what was
   tried and dropped, what costs too much to run. And the other end: what has ground but no
   collected cases yet.

## Pass one: the claims

### 1. Find every fact yourself first

**Never ask what the repo can tell you.** Finding facts is your job. The decisions are theirs.

Read how the system starts, what tools it has, and what it returns. Then read what is already
written down:

```
README* CLAUDE.md AGENTS.md docs/ evals/ tests/ fixtures/ runs/ and the git log of fixes
```

- **Labelled data** already in the repo is the richest seam. Find out who or what wrote each
  label: a script over real history, a person, or a model.
- **Earlier run folders** show what is saturated. A set the strongest model scores everything
  on cannot show an improvement.
- **Do not block on it.** Where subagents are available, send the reading out as one and open
  the first questions meanwhile. What comes back arrives as claims to confirm, never as blanks
  for them to fill.

### 2. Survey them in multiple choice

The interview is `/grilling`'s, if that skill is installed: a design tree, a frontier, a
recommended answer under every question, and no action until the user confirms. What follows
restates it so this skill works alone.

**Every question is a multiple choice, and it goes through `AskUserQuestion`.** Never a wall of
prose questions.

- **One to four questions a call,** and only ones whose wording would not change with an
  answer in the same batch. Send one alone when its answer would rewrite the others.
- **Two to four options, each a position someone could hold.** If you cannot name a second
  real position, state it as a claim to correct.
- **The recommended option first,** labelled `(Recommended)`.
- **Each option names its consequence.** "Mined from re-runs: the answer is then something the
  system is never shown" beats "from re-runs".
- **Never write an "Other" option.** It is supplied, and it is where corrections arrive.
- **`multiSelect` when answers are not exclusive.**
- **Re-derive the next batch from the answers you just got.** Do not pre-write the survey.

The stages the walk passes through, in dependency order:

1. **The stakes.** Who reads the score and what they do with it. What one task is. What the
   system is for.
2. **The ground.** Where answers come from, who wrote them, and how many there are of each
   kind. What the system is shown, and whether each answer can be reached from it.
3. **The claims.** Their list, in their words, plus the ones the repo suggests. Per claim: the
   classes, the grader, and what would make its score a lie.
4. **The fences.** What is saturated, dropped, too costly, or off limits. What has ground and
   no cases.
5. **The evals.** Last, with the whole list in view: **which of these claims are one eval?**
   proofbench grades one answer per task, with one grader per eval. Two answers to the same
   input are two evals. An answer and the way it was reached are one eval that grades a path.

**Stop when what is left would not change what `/proofbench` builds.** That is usually five to
twelve entries, and always sooner than an empty frontier.

### 3. Push back

- **A claim phrased as a metric goes back.** "I want accuracy on the ticket set" names a
  number. Ask what the system is supposed to get right, and what they would do if it did not.
- **An answer key with no source is not ground.** Take it, and record it as stated and
  unverified, with the date.
- **"It depends" is an answer not yet given.** Ask what it depends on. That is usually a class
  they had not named, or an ambiguous task.
- **A claim whose answer the system cannot reach is not testable,** however good its labels.
  Move it down and say what the system would have to be shown.
- **A claim with no honesty condition is not finished.** If neither of you can name a way its
  score could lie, say so in the entry.

### 4. Write it

**Not before they confirm.** Summarise what you now believe in a dozen lines, and ask whether
that is a shared understanding. Then follow `references/docket-format.md` and write
`evals/docket.md`, unless they name another path.

Read it back against these, and fix what fails:

- Every entry has **Ground**, **Shown**, **Grader** and **Honesty**.
- Every count and every score carries its number and the date it was taken.
- **"Not testable, and why" is not empty.** If nothing was ruled out, nothing was tested.
- A claim with ground and no collected cases is in "Testable once harvested".
- Every entry in "One eval, several claims" names its eval folder.
- Nothing in the file is a fact you invented. Read from the repo, quoted from them, or absent.

Hand back the path, the entry count, the sharpest thing you learned that the repo could not
have told you, and anything they left unknown.

## Pass two: the ambiguous tasks

A task with two defensible answers is a coin the system flips. Graded as written, it reads as
a failure of the system when it is a fault in the eval.

1. **Find the candidates yourself, for free.** Never start a run to find them. If a run would
   help, say what it costs and leave it to `/proofbench`.
   - *From run folders that already exist:* a miss whose answer held the expected thing
     beside another, a task right on one trial and wrong on the next (`unstable_questions`),
     and a judge's `why` that turns on wording.
   - *From the tasks:* a scope word that reads two ways ("the user", "every user"), an
     expected answer that is part of another task's, and an expected answer of none.
2. **Put each one to the owner, one at a time.** Show the task, its expected answer, and the
   real answer that exposed it. The options are the readings, each with its consequence:
   count it right, count it wrong, or the task is at fault. Recommend one.
3. **Put the ruling where a command can hold the grader to it.** In order of preference:
   - a hand-written control with its prediction, written before anything is graded;
   - a line in the rubric, when a judge grades;
   - a change to the answer or the harvester. This turns gates stale, so say which ones and
     what earning them again costs, and wait for a yes.
4. **Record it** under "Rulings on ambiguous tasks" in the docket: the task, the readings, the
   ruling, its date, and where it was put into effect.

You never rule. A task they will not rule on stays in the docket as open.

## What /proofbench does with it

Say this when you hand it over.

- **It guides.** The docket supplies the classes, the source the harvester mines, the grader
  for each eval, the path rules, the rulings that become controls, and the list of what not to
  build.
- **It does not rule.** Commands still decide every gate. A claim the docket calls testable
  has not passed headroom.
- **When the two disagree, the gates win on facts and the docket wins on meaning.** A claim
  filed as testable that fails headroom at 0 moves to "Not testable", with the score. What a
  class means, and which reading of a task is right, are the docket's.

## Rules

- **Read, quoted, or absent.** Every fact came from the repo, came from the user with
  attribution, or is not in the file.
- **One entry per claim, and it grows in place.** Git log is the history. Addresses such as
  `C3` are never reused.
- **Testable means the ground exists, the cases are collected, and the answer can be
  reached.** Interesting has nothing to do with it.
- **Do not resolve their disagreements with themselves.** Put the conflict in the file as an
  open question.
- **Never change a prediction to match a grade.**
- **Ask in multiple choice, one to four a call,** with a recommendation first.
- **Spend nothing.**
