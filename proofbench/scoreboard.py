"""Question scoreboard: the numbers the study reads, and the grid it reads them in.

Every metric is computed from the per question records, so any question field can be a
grouping key and a saved scoreboard can be regrouped later without re-running an arm.

The provenance of a leg sits above its numbers, because a number is worth nothing until the
reader knows whether a model or a canned reply produced it. The registry scans this file for
the stub marker, so the marker has to reach it or the refusal has nothing to refuse on.

A leg whose questions hold nothing answerable measured abstention and nothing else, so it is
given no key named accuracy and no key named tokens_per_correct. A reader lifts the word, never
the caveat printed beside it, and the one word a corpus of verified absences can carry is
abstention.

A question asked more than once has one record per trial, all under its id. accuracy then
counts trials, and pass^k and pass@k say how the trials of one question agree: a leg that is
right on average and a leg that is right every time are different legs."""
from math import comb

from .util import die

# The stratification the PRD fixes: three tiers crossed with five hop depths, fifteen cells.
# The grid takes its axes from here and never from the keys the records happen to carry, so a
# cell holding no question prints empty rather than vanishing out of a complete looking table.
STRATIFICATION = {"tier": (1, 2, 3), "hops": (1, 2, 3, 5, 7)}
NO_QUESTION, NO_NUMBER = ".", "-"
LEGEND = f"{NO_QUESTION} no question in this cell, {NO_NUMBER} no such number on this cell"


def _rate(hits, total):
    return round(hits / total, 3) if total else None


def _tokens(records):
    return sum(record["tokens_in"] + record["tokens_out"] for record in records)


def _price(tokens, correct):
    """None, never zero, when nothing was correct: the ratio is undefined there, and a zero
    would read as a perfect price."""
    return round(tokens / correct, 1) if correct else None


def _score_answers(records, tokens):
    """The two words that mean something only once an answerable question has been asked."""
    correct = sum(record["correct"] for record in records)
    return {"correct": correct, "accuracy": _rate(correct, len(records)),
            "tokens_per_correct": _price(tokens, correct)}


def _score_abstentions(records, tokens):
    """The same two numbers under the only names they can honestly carry when every question
    was unanswerable: every correct grade there was a refusal to answer, not an answer."""
    correct = sum(record["correct"] for record in records)
    return {"correct_abstentions": correct, "abstention_rate": _rate(correct, len(records)),
            "tokens_per_correct_abstention": _price(tokens, correct)}


def _abstention_rates(answerable, unanswerable):
    """Two different facts, never one: refusing where an answer exists is a miss, and refusing
    where none exists is the correct answer. The answerable rate counts the arms that did not
    abstain, which is not the same as the arms that were right, so it is not named correct."""
    return {
        "non_abstention_rate_answerable":
            _rate(sum(1 for record in answerable if not record["abstained"]), len(answerable)),
        "abstention_correct_unanswerable":
            _rate(sum(1 for record in unanswerable if record["abstained"]), len(unanswerable)),
    }


def gather_trials(records):
    """Every trial of one question under its id. Each question has to have been asked the same
    number of times, or a rate over them compares nothing, so an unequal count is a hard stop."""
    questions = {}
    for record in records:
        questions.setdefault(record["id"], []).append(record)
    counts = {len(attempts) for attempts in questions.values()}
    if len(counts) != 1:
        die(f"questions were asked unequal numbers of times: {sorted(counts)}")
    return questions


def _pass_rates(questions, trials, prefix):
    """pass^k is the chance that k trials of one question are all correct, and pass@k the chance
    that at least one is, each averaged over the questions. With c of n trials correct,
    C(c,k)/C(n,k) and 1 - C(n-c,k)/C(n,k) estimate them without bias for every k up to n, so one
    run of n trials yields the whole curve. pass^1 and pass@1 are both the per trial rate."""
    corrects = [sum(attempt["correct"] for attempt in attempts) for attempts in questions.values()]
    rates = {}
    for k in range(1, trials + 1):
        draws = comb(trials, k) * len(corrects)
        rates[f"{prefix}pass^{k}"] = _rate(sum(comb(c, k) for c in corrects), draws)
        rates[f"{prefix}pass@{k}"] = _rate(draws - sum(comb(trials - c, k) for c in corrects), draws)
    return rates


def _find_unstable(questions):
    """The questions answered both right and wrong across their trials. They are what separates
    pass^k from pass@k, and the ones to read first: the arm, not the question, changed."""
    return sorted(question_id for question_id, attempts in questions.items()
                  if 0 < sum(attempt["correct"] for attempt in attempts) < len(attempts))


def metrics(records):
    """What this set of records measured, under names it can carry. The answerable and the
    unanswerable counts print on every leg, because they are what decides whether the rate
    beside them is an accuracy at all. They count questions, never trials."""
    answerable = [record for record in records if record["answerable"]]
    unanswerable = [record for record in records if not record["answerable"]]
    questions = gather_trials(records)
    trials = len(records) // len(questions)
    tokens = _tokens(records)
    score = _score_answers if answerable else _score_abstentions
    return {
        "questions": len(questions),
        "trials": trials,
        "answerable": len({record["id"] for record in answerable}),
        "unanswerable": len({record["id"] for record in unanswerable}),
        "measures": "accuracy and abstention" if answerable else "abstention only",
        **score(records, tokens),
        **_pass_rates(questions, trials, "" if answerable else "abstention_"),
        "unstable_questions": _find_unstable(questions),
        **_abstention_rates(answerable, unanswerable),
        "tokens_in": sum(record["tokens_in"] for record in records),
        "tokens_out": sum(record["tokens_out"] for record in records),
        "tokens_total": tokens,
    }


def _was_stubbed(records):
    """True when a canned reply answered any question, None when no arm said either way.

    None rather than False: an arm that never reports was never measured to be a measurement,
    and writing False there would put that claim in the file on the arm's behalf. One canned
    answer stubs the whole leg, because every leg number is summed over every question."""
    said = [record["stubbed"] for record in records if record["stubbed"] is not None]
    return any(said) if said else None


def _find_answering_model(records):
    """The one model id the arm reported. Two in one leg is a hard stop: the leg's numbers are
    summed over every question, and a sum across two models measures neither of them."""
    models = {record["model"] for record in records if record["model"] is not None}
    if len(models) > 1:
        die(f"one leg was answered by more than one model: {sorted(models)}")
    return models.pop() if models else None


def _sum_leg_cost(records):
    """None, never zero, when no arm reported a cost: unreported and free are different facts."""
    costs = [record["cost_usd"] for record in records if record["cost_usd"] is not None]
    return round(sum(costs), 6) if costs else None


def _why_not_measured(stubbed, cost):
    """Measured is a positive claim, so silence is one of the reasons against it. Reading an
    unreported stub marker and an unreported cost as two denials is what declared a leg nobody
    vouched for a measurement: absence of evidence, read as evidence."""
    reasons = []
    if stubbed is None:
        reasons.append("no arm said whether a canned reply answered it")
    elif stubbed:
        reasons.append("canned replies answered at least one question")
    if cost is None:
        reasons.append("no arm reported what the leg cost")
    elif cost == 0:
        reasons.append("the whole leg cost 0 USD")
    return reasons


def describe_provenance(records):
    """What produced these numbers, written above them so a canned leg cannot be read as a
    measured one. A leg costing exactly zero is a stub or a bug, and neither is a measurement."""
    stubbed, cost = _was_stubbed(records), _sum_leg_cost(records)
    reasons = _why_not_measured(stubbed, cost)
    return {"stubbed": stubbed, "model": _find_answering_model(records), "cost_usd": cost,
            "is_measured": not reasons, "not_measured_why": reasons}


def group(records, fields):
    """Group records by a tuple of question fields, for example ("tier", "hops"). A field no
    question carries raises, because a grid with a silently empty axis measures nothing."""
    cells = {}
    for record in records:
        key = tuple(record["question"][field] for field in fields)
        cells.setdefault(key, []).append(record)
    return {key: metrics(rows) for key, rows in cells.items()}


def _axis(field):
    """Axes come from the stratification, never from the data: a grid drawn over the keys that
    happen to be present shows two cells of fifteen and still reads as a whole table."""
    return STRATIFICATION.get(field) or die(
        f"'{field}' is not a stratification axis (have {sorted(STRATIFICATION)})")


def _cell(cell, metric):
    """An empty cell and a cell that cannot carry this number are different facts, and a grid
    printing both the same way hides one of them."""
    if not cell:
        return NO_QUESTION
    value = cell.get(metric)
    return NO_NUMBER if value is None else f"{value}"


def _refuse_questions_off_the_axes(cells, rows, columns):
    outside = sorted(key for key in cells if key[0] not in rows or key[1] not in columns)
    if outside:
        die(f"questions sit outside the stratification, so no grid holds them: {outside}")


def grid(records, row_field, column_field, metric):
    """One metric over every cell the stratification names, as text. The metric is named above
    the table, because a number in a cell does not say what it is and the reader carries the
    heading away with it."""
    cells = group(records, (row_field, column_field))
    rows, columns = _axis(row_field), _axis(column_field)
    _refuse_questions_off_the_axes(cells, rows, columns)
    header = f"{row_field:>10} | " + " ".join(f"{column_field}={column}".ljust(9)
                                              for column in columns)
    lines = [f"{metric} by {row_field} x {column_field}", header, "-" * len(header)]
    for row in rows:
        values = (_cell(cells.get((row, column)), metric) for column in columns)
        lines.append(f"{row:>10} | " + " ".join(value.ljust(9) for value in values))
    return "\n".join(lines + [LEGEND])
