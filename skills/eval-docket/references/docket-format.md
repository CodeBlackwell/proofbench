# The docket format

One file, `evals/docket.md`. Eight sections in this order, and four fields on every entry.
`/proofbench` reads the fields straight into an eval's config, so an entry missing a field is
an eval missing a decision.

```
# The eval docket: <what the system is>

<preamble: one paragraph. What one entry is, the date the file was begun, and the rule
that it grows in place. Git log is the history, so no changelog lives inside it.>

## What the system is shown, and what it returns
## The rules that bind every eval
## The vocabulary            (only if the domain has terms a reader would get wrong)
## Testable now
## One eval, several claims
## Testable once harvested
## Not testable, and why
## Rulings on ambiguous tasks
```

**Three buckets, not two.** A claim is testable now, testable once its cases are collected, or
not testable. Filed as testable, an unharvested claim implies tasks nobody has. Filed as not
testable, it hides work that is one script away.

## What the system is shown, and what it returns

- **The unit:** what one task is, in the owner's words.
- **Shown:** everything the system receives for a task, and every tool it can call.
- **Returns:** a change to a repo, an answer in words, or an id from a fixed list.
- **Started by:** the one command that runs it headless, or what stands in the way of one.

Every "Shown" field below refers back here.

## The rules that bind every eval

The short list that applies to every entry, stated once. Typically:

- **Where answers come from,** each source named with who or what wrote it and how many it
  holds. Answers a model wrote are listed apart, with how many the owner has approved.
- **The classes that must never be merged,** and the common one a lazy system could always say.
- **Whether declining is an answer,** and when it is the right one.
- **Known leaks:** what in a task, a fixture or the history would hand the system its answer.
- **What a run costs,** when the owner has a figure: model, tasks, trials, dollars, date.

## Testable now

Numbered `C1`, `C2`, ... The number is an address other documents cite. It is never reused and
never renumbered. A retired claim is struck in place.

Each entry is a claim **stated the way its owner says it out loud**, then four fields.

> **C1. It sends a ticket to the queue a person would.** Ground: 1,840 tickets a person moved
> to another queue, mined by script. Shown: the ticket's subject and body, which is what the
> person had. Grader: exact id, one of six queues. Honesty: 61% are billing, so always saying
> billing scores 0.61; read each queue on its own.

| Field | What it holds | What fails |
|---|---|---|
| **Ground** | Where the known answers come from, how many there are, and how many of each class | "We have labels": if their source cannot be named, the claim is not testable yet |
| **Shown** | What the system receives for this claim, and whether the answer can be reached from it | Leaving it out because it seems obvious. This is where an unpassable eval is caught |
| **Grader** | A command, an exact id, a judge with a rubric, or a path rule | "Accuracy". That is a number, and says nothing of who decides right |
| **Honesty** | What makes this score a lie: imbalance, a leak, noise, an invented key, saturation | Omitting the field because none was found. Say that instead |

- A score, once one has been taken, goes in the entry with its model, its task count, its
  trials and its date.
- An entry may hold more than the four fields. It never holds fewer.

## One eval, several claims

Which entries above share an eval folder, and which need their own.

- **One grader per eval.** Claims graded differently are different evals.
- **One answer per task.** Two answers to the same input are two evals over the same tasks.
- **An answer and the way it was reached are one eval,** which grades a path.

Per eval: its folder under `evals/`, the claims it carries, and its task kind.

## Testable once harvested

Claims whose ground exists and whose cases nobody has collected. No `C` address yet: the first
collected task set earns one.

Each names the source its harvester would mine, a rough count if one is known, and the honesty
conditions it will inherit from the entries it descends from.

## Not testable, and why

A bullet per claim that was ruled out, with the reason. Four kinds:

- **Out of reach.** The answer cannot be reached from what the system is shown. Say what it
  would have to be shown.
- **No ground.** No known answers exist. Say what history would supply them.
- **Saturated.** The strongest model already scores everything. Name the model, the score and
  the date.
- **Out of scope by decision.** Say who decided, and when.

**This section is never empty in a real docket.**

## Rulings on ambiguous tasks

One entry per task that had more than one defensible answer.

> **`T-0412`, ruled 2026-11-21.** Expected billing. The agent answered login, and the ticket
> asks about both. Readings: either queue is right; only the queue the person chose is right.
> Ruling, by the owner: only the queue the person chose. In effect: control
> `T-0412/other-queue`, predicted 0.

- A task nobody has ruled on stays here, marked **open**.
- A ruling that changed an answer says which gates it turned stale.

## A skeleton

Illustrative shape only. The numbers are invented and no system is behind them.

```markdown
# The eval docket: the support desk agent

Begun 2026-11-21. One entry per claim an eval can test: the ground its answers stand on, what
the agent is shown, the grader, and the honesty conditions. Addresses are never reused. Grows
in place; git log is the history.

## What the system is shown, and what it returns

- **The unit:** one incoming ticket.
- **Shown:** the ticket's subject and body, and a `search_orders` tool.
- **Returns:** a queue id from a list of six, and a drafted reply.
- **Started by:** `./agent.sh --ticket FILE`.

## The rules that bind every eval

- **Answers come from re-routing history:** 1,840 tickets a person moved to another queue,
  mined by script on 2026-11-20. No answer was written by a model.
- **Billing is 61% of tickets.** Always saying billing scores 0.61.
- **The agent may decline.** Declining is right only for the 112 tickets a person closed as
  not a request.

## Testable now

**C1. It sends a ticket to the queue a person would.** Ground: 1,840 re-routed tickets, 6
queues, 61% billing. Shown: subject and body, which is what the person had. Grader: exact id.
Honesty: a re-route records where the ticket ended, and 9% were moved twice; read per queue.

## One eval, several claims

- **`evals/routing/`** carries C1 alone. A question eval, graded by exact id, with no judge.

## Testable once harvested

- **Its reply states the right refund amount.** Ground: the amounts actually refunded, in the
  orders export. Nobody has joined them to tickets. Inherits C1's billing imbalance.

## Not testable, and why

- **Whether a ticket will reopen.** Out of reach: the label is what happened days later, and
  nothing the agent is shown says it.
- **Tone of the reply.** Out of scope by decision, 2026-11-21: nobody acts on it.

## Rulings on ambiguous tasks

- **`T-0931`, open.** The ticket asks about a charge and a login. A person chose billing.
```
