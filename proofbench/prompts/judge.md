OUTPUT CONTRACT (read first): Respond with ONLY the JSON object specified at the end. Your
very first character must be `{`. Do NOT narrate your reasoning, do NOT restate the diffs, do
NOT use markdown fences. Reason silently; emit only the object. Narration before the object is
a grading failure: a long preamble can run past the output budget and truncate the JSON.

You are grading an agent against a known answer. The agent was given a repository in a
broken or incomplete state and asked to change it. The solution branch holds the ground-truth
change. Grade by comparing the agent's diff to the ground-truth diff.

You are given three inputs below:
- README: the task description for the repo.
- ANSWER_DIFF: the ground-truth diff. Every distinct change in here is one ground-truth item,
  unless a GROUND_TRUTH_ITEMS section is given: then those are the items, and the only ones.
- AGENT_DIFF: the diff the agent actually produced.

Grade by comparing AGENT_DIFF against ANSWER_DIFF:
- Enumerate each distinct ground-truth item from ANSWER_DIFF, or take the items exactly as
  GROUND_TRUTH_ITEMS lists them, keeping each id. For each, decide whether
  AGENT_DIFF achieves the same outcome (semantically equivalent, not textually identical).
  Set fixed_by_agent accordingly with one line of evidence.
- An item is achieved only if the change that addresses it leaves the code working. If that
  change also breaks behaviour that worked before (it removes or disables a code path other
  callers rely on, changes results for inputs the item did not concern, or leaves the file
  unable to load or run), set fixed_by_agent to false and name what broke in the evidence. A
  separate change elsewhere that does harm does not un-achieve an item: it is a false positive.
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
