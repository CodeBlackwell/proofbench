The demo's grading prompt, and nothing a study should grade against. This demo's arm answers
tier 1 from the answer key and abstains everywhere else, so every question is settled by an
exact id match or by abstention and the judge is never reached. A real question corpus supplies
its own rubric here: an answer rubric knows the domain it grades, so proofbench ships none.

OUTPUT CONTRACT (read first): respond with ONLY the JSON object below. Your very first character
must be `{`. Do not narrate, do not restate the question, do not use markdown fences. Narration
before the object is a grading failure: a preamble can run past the output budget and truncate
the JSON.

Grade AGENT_ANSWER against EXPECTED. correct is 1 when the agent names what the expected answer
names, and 0 when it names something else, answers only part of it, or says it does not know
while the expected answer exists. correct is 1 or 0 and nothing else: the harness reads it as a
count of correct answers, so a fraction is a grading failure.

{
  "correct": 1,
  "why": "one sentence naming what the agent said and why it does or does not match"
}
