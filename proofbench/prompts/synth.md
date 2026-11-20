You are improving a subject artifact — the instructions an agent follows to perform a task.
The current subject was evaluated against several ground-truth tasks and scored by comparing
the agent's output to each task's answer key.

You are given below:
- GRADES: the per-task grade JSON (ground-truth items, which were achieved/missed, false
  positives, notes).
- CURRENT_SUBJECT: the full current text of the subject artifact.

Study the GRADES for SYSTEMATIC weaknesses — failure classes the subject repeatedly misses,
and patterns of noise or over-doing. Then rewrite the subject with MINIMAL, targeted changes
that address them. Preserve the subject's structure and intent. Do not bloat it; surgical
edits only. Note: a weak driver model often ignores prose caution and edits less — so prefer
changes that supply concrete reasoning or checklists over changes that only add warnings.

Output ONLY a single JSON object, no prose, no markdown fences:
{
  "changelog": "bullet list of what you changed and which grade miss each change targets",
  "subject": "the complete new subject artifact contents"
}
