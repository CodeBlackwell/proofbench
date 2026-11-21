"""LLM judge: compare the agent's artifact to ground truth and emit numeric metrics.

A grade with no numeric metric is a hard stop, not a zero. Failing loud here is the
whole point: an empty grade that flows onward manufactures false confidence."""
import json

from .util import claude_json, die


def numeric_fields(grade):
    return {k: v for k, v in grade.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


ITEMS_RULE = """===== GROUND_TRUTH_ITEMS =====
This task fixes its own ground-truth items. They are listed below, one id each, and they are the
only items: do not add, split, merge or drop any, whatever else ANSWER_DIFF changes. A change in
ANSWER_DIFF that belongs to no listed item is not an item and never counts against the agent.
Return exactly one entry per id in "items", each with "fixed_by_agent" set to true or false."""


def _list_items(items):
    listed = "\n".join(f"i{number}: {item}" for number, item in enumerate(items, 1))
    return f"{ITEMS_RULE}\n{listed}\n\n" if items else ""


def _recall_over(items, result):
    """Recall over the items the task listed, counted here. The judge rules on each item and
    nothing more: it does not choose how many items there are, and it does not do the division.
    A reply that does not rule on exactly the listed ids is a hard stop."""
    ruled = result.get("items")
    entries = ruled if isinstance(ruled, list) else []
    verdicts = {entry.get("id"): entry.get("fixed_by_agent") for entry in entries if isinstance(entry, dict)}
    expected = {f"i{number}" for number in range(1, len(items) + 1)}
    is_exact = len(entries) == len(items) and set(verdicts) == expected
    if not is_exact or any(not isinstance(fixed, bool) for fixed in verdicts.values()):
        die(f"judge did not rule true or false on exactly the items {sorted(expected)}: {ruled}")
    return sum(verdicts.values()) / len(items)


def ask(prompt, model, limit_kb, name):
    """One oversized agent diff once cost $4.50 to grade. An input over the limit stops the run
    and names what it was for: cut to fit, it would be graded on part of the evidence."""
    size_kb = len(prompt.encode()) / 1024
    if limit_kb is not None and size_kb > limit_kb:
        die(f"judge input for {name} is {size_kb:.0f} KB, over judge_input_limit_kb ({limit_kb})")
    return claude_json(prompt, model)


def grade(judge_prompt, readme, answer_diff, agent_diff, model, items=(), limit_kb=None,
          name="this task"):
    """The judge's reply, and what asking for it cost."""
    prompt = (f"{judge_prompt}\n\n{_list_items(items)}"
              f"===== README =====\n{readme}\n\n"
              f"===== ANSWER_DIFF =====\n{answer_diff}\n\n"
              f"===== AGENT_DIFF =====\n{agent_diff}\n")
    result, cost_usd = ask(prompt, model, limit_kb, name)
    if items:
        result["recall"] = _recall_over(items, result)
    if not numeric_fields(result):
        die("judge returned no numeric metric")
    return result, cost_usd


def grade_answer(judge_prompt, question, result, model, limit_kb=None):
    """Grade one prose answer against the known answer. Only reached when an exact id match
    could not settle the question, so the judge reads words and numbers written as words,
    never ids. A verdict that is not 1 or 0 is a hard stop, exactly as an empty grade is.
    Returns the verdict and what asking for it cost."""
    expected = {"answer": question["answer"], "answer_names": question.get("answer_names", [])}
    prompt = (f"{judge_prompt}\n\n"
              f"===== QUESTION =====\n{question['text']}\n\n"
              f"===== EXPECTED =====\n{json.dumps(expected, ensure_ascii=False)}\n\n"
              f"===== AGENT_ANSWER =====\n{result.get('answer', '')}\n\n"
              f"===== AGENT_ANSWER_IDS =====\n{json.dumps(result['answer_ids'], ensure_ascii=False)}\n")
    verdict, cost_usd = ask(prompt, model, limit_kb, question["id"])
    if verdict.get("correct") not in (0, 1):
        die(f"answer judge returned no binary 'correct' on {question['id']}: {verdict}")
    return verdict, cost_usd
