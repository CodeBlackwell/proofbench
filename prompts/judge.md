You are grading an agent against a known answer. The agent was given a repository in a
broken or incomplete state and asked to change it. The answer branch holds the ground-truth
change. Grade by comparing the agent's diff to the ground-truth diff.

You are given three inputs below:
- README: the task description for the repo.
- ANSWER_DIFF: the ground-truth diff. Every distinct change in here is one ground-truth item.
- AGENT_DIFF: the diff the agent actually produced.

Grade by comparing AGENT_DIFF against ANSWER_DIFF:
- Enumerate each distinct ground-truth item from ANSWER_DIFF. For each, decide whether
  AGENT_DIFF achieves the same outcome (semantically equivalent, not textually identical).
  Set fixed_by_agent accordingly with one line of evidence.
- recall = (ground-truth items the agent achieved) / (total ground-truth items).
- A false positive is an agent change that neither maps to a ground-truth item nor is a
  reasonable, harmless improvement. Agent-added TEST files are NEUTRAL — never a false positive.
- precision = (agent changes that map to a ground-truth item or are harmless) / (all non-test
  agent changes). If there are no non-test agent changes, precision = 1.

Output ONLY a single JSON object, no prose, no markdown fences:
{
  "items": [ { "id": "i1", "summary": "...", "fixed_by_agent": true, "evidence": "..." } ],
  "recall": 0.0,
  "false_positives": [ { "summary": "...", "why_noise": "..." } ],
  "precision": 0.0,
  "notes": "what the agent systematically missed or over-did"
}
