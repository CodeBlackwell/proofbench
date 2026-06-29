"""LLM judge: compare the agent's artifact to ground truth and emit numeric metrics.

A grade with no numeric metric is a hard stop, not a zero. Failing loud here is the
whole point: an empty grade that flows onward manufactures false confidence."""
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
