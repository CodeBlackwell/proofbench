"""LLM judge: compare the agent's artifact to ground truth and emit numeric metrics.

A grade with no numeric metric is a hard stop, not a zero. Failing loud here is the
whole point: an empty grade that flows onward manufactures false confidence."""
import json

from .util import claude_json, die


def numeric_fields(grade):
    return {k: v for k, v in grade.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


def grade(judge_prompt, readme, answer_diff, agent_diff, model):
    prompt = (f"{judge_prompt}\n\n"
              f"===== README =====\n{readme}\n\n"
              f"===== ANSWER_DIFF =====\n{answer_diff}\n\n"
              f"===== AGENT_DIFF =====\n{agent_diff}\n")
    result = claude_json(prompt, model)
    if not numeric_fields(result):
        die("judge returned no numeric metric")
    return result


def grade_answer(judge_prompt, question, result, model):
    """Grade one prose answer against the known answer. Only reached when an exact id match
    could not settle the question, so the judge reads words and numbers written as words,
    never ids. A verdict that is not 1 or 0 is a hard stop, exactly as an empty grade is."""
    expected = {"answer": question["answer"], "answer_names": question.get("answer_names", [])}
    prompt = (f"{judge_prompt}\n\n"
              f"===== QUESTION =====\n{question['text']}\n\n"
              f"===== EXPECTED =====\n{json.dumps(expected, ensure_ascii=False)}\n\n"
              f"===== AGENT_ANSWER =====\n{result.get('answer', '')}\n\n"
              f"===== AGENT_ANSWER_IDS =====\n{json.dumps(result['answer_ids'], ensure_ascii=False)}\n")
    verdict = claude_json(prompt, model)
    if verdict.get("correct") not in (0, 1):
        die(f"answer judge returned no binary 'correct' on {question['id']}: {verdict}")
    return verdict
