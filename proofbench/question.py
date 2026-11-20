"""The question task kind: one question in on stdin, one answer object out, graded by id.

Beside the repo task and sharing nothing with it. There is no repository and no diff: the
corpus is a JSONL file of questions with known answers, the runner is any executable holding
one arm of the study, and the grade is an exact id match first, the LLM judge only when prose
or a number written as words has to be read. An abstention is correct exactly when the
question is not answerable."""
import json
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from . import judge, runner, scoreboard
from .util import die, log


# The fields the grade and the grid read, and the type each has to be. A question without one
# would stop the leg only after its arm had been paid for.
REQUIRED = {"id": str, "text": str, "answer": list, "answerable": bool, "tier": int, "hops": int}


def _read_line(path, number, line):
    try:
        record = json.loads(line)
    except json.JSONDecodeError as err:
        die(f"{path}:{number} is not JSON: {err}")
    wrong = [field for field, kind in REQUIRED.items()
             if not isinstance(record, dict) or not isinstance(record.get(field), kind)]
    return record if not wrong else die(f"{path}:{number} is missing or mistypes {wrong}")


def load(path):
    """One question per line, in the shape the study's question format fixes."""
    lines = enumerate(path.read_text().splitlines(), 1)
    questions = [_read_line(path, number, line) for number, line in lines if line.strip()]
    return questions or die(f"question file holds no questions: {path}")


def normalise(value):
    """Ids compare case, whitespace and Unicode form insensitively; nothing else about them is
    touched. NFC because the DiVA snapshot holds one supervisor, Gutierrez-de-Teran, under a
    decomposed spelling and a composed one that print identically, and two ids a reader cannot
    tell apart must not reach the judge as though they named different people. Folding the
    diacritics away, or the punctuation, would merge names that really are different."""
    return unicodedata.normalize("NFC", " ".join(str(value).strip().lower().split()))


def ids_match(question, result):
    expected = {normalise(one) for one in question["answer"]}
    answered = {normalise(one) for one in result["answer_ids"]}
    return bool(expected) and expected == answered


def grade_one(cfg, question, result, judge_model):
    """Abstention decides first, then an exact id match, and only then the judge."""
    if result["abstained"] or not question["answerable"]:
        correct = int(bool(result["abstained"]) and not question["answerable"])
        return {"correct": correct, "graded_by": "abstention"}
    if ids_match(question, result):
        return {"correct": 1, "graded_by": "exact"}
    verdict, cost_usd = judge.grade_answer(cfg.judge_prompt, question, result, judge_model)
    return {"correct": int(verdict["correct"]), "graded_by": "judge",
            "judge_why": verdict.get("why", ""), "judge_cost_usd": cost_usd}


def _ask_and_grade(cfg, question, trial, model, out_dir):
    """The arm's own report of how it answered travels with the grade. An arm that says it read
    a canned reply is the only thing downstream can learn that from, so dropping "stubbed" here
    is what let a canned leg reach the registry looking like a measurement."""
    result = runner.ask(cfg.runner, model, question, out_dir / "run.log", cfg.runner_args,
                        cfg.timeout_minutes)
    record = {"id": question["id"], "trial": trial,
              **grade_one(cfg, question, result, cfg.judge_model),
              "abstained": bool(result["abstained"]),
              "answer_ids": result["answer_ids"], "answer": result.get("answer"),
              "answerable": bool(question["answerable"]),
              "tokens_in": result["tokens_in"], "tokens_out": result["tokens_out"],
              "cost_usd": result.get("cost_usd"), "seconds": result.get("seconds"),
              "stubbed": result.get("stubbed"), "model": result.get("model"),
              "question": question}
    (out_dir / "result.json").write_text(json.dumps({"result": result, "grade": record}, indent=2))
    return record


def _leg(cfg, questions, model, run_dir):
    """Every question is asked cfg.trials times, each trial a fresh arm process that knows
    nothing of the others, so the trials of one question are independent draws."""
    log(f"leg [{model}] {len(questions)} questions x {cfg.trials} trials, "
        f"concurrency {cfg.concurrency}")
    attempts = [(question, trial) for question in questions
                for trial in range(1, cfg.trials + 1)]
    with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
        def work(attempt):
            question, trial = attempt
            out_dir = run_dir / model / question["id"] / f"trial-{trial}"
            out_dir.mkdir(parents=True, exist_ok=True)
            return _ask_and_grade(cfg, question, trial, model, out_dir)
        records = list(pool.map(work, attempts))
    leg = {**scoreboard.describe_provenance(records), **scoreboard.metrics(records),
           "records": records}
    (run_dir / model).mkdir(parents=True, exist_ok=True)
    (run_dir / model / "scoreboard.json").write_text(json.dumps(leg, indent=2))
    return leg


def describe_misses(records):
    """What a rewrite of the subject can learn from: every question the arm got wrong at least
    once, with what was expected and what each trial answered. A question answered right on
    every trial teaches nothing, so it is left out. Only the fields the question contract fixes
    are shown, so a corpus's private notes on its answers never reach the rewrite."""
    blocks = []
    for attempts in scoreboard.gather_trials(records).values():
        if all(attempt["correct"] for attempt in attempts):
            continue
        question = attempts[0]["question"]
        shown = ("trial", "correct", "abstained", "answer_ids", "answer")
        miss = {"question": question["text"], "expected_ids": question["answer"],
                "expected_names": question.get("answer_names", []),
                "answerable": question["answerable"],
                "trials": [{key: attempt[key] for key in shown} for attempt in attempts]}
        blocks.append(f"--- {question['id']} ---\n{json.dumps(miss, indent=2, ensure_ascii=False)}")
    return "\n".join(blocks)


def _refuse_shared_ids(questions):
    """Trials are gathered by question id, so two questions sharing one would be scored as two
    trials of a single question."""
    ids = [question["id"] for question in questions]
    shared = sorted({one for one in ids if ids.count(one) > 1})
    if shared:
        die(f"question ids are not unique: {shared}")


def _refuse_off_the_grid(questions):
    """The grid is printed after the run, so a question it has no cell for is refused here,
    before the run is spent."""
    axes = scoreboard.STRATIFICATION
    outside = sorted(question["id"] for question in questions
                     if any(question[field] not in axes[field] for field in axes))
    if outside:
        die(f"questions sit outside the stratification {axes}: {outside}")


def read(cfg):
    """Every question of the corpus, checked whole. No arm is asked here."""
    questions = [question for task in cfg.corpus for question in load(task.path)]
    _refuse_shared_ids(questions)
    _refuse_off_the_grid(questions)
    return questions


def bench(cfg, run_dir, models):
    """The question leg of the bench, one leg per answering model, mirroring engine.bench."""
    questions = read(cfg)
    board = {model: _leg(cfg, questions, model, run_dir) for model in models}
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "scoreboard.json").write_text(json.dumps(board, indent=2))
    return board
