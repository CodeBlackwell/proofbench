#!/usr/bin/env python3
"""A stub arm, for the demo and the tests only. It measures nothing.

The harness hands an arm a question's id and text and never its answer, so this arm opens the
demo's own key file, which a real arm has no path to. It answers tier 1 from the key and
abstains everywhere else, so the fixture grades to known accuracy and abstention numbers
offline: no API key, no network, no `claude` CLI."""
import json
import sys
from pathlib import Path

KEY = Path(__file__).resolve().parent.parent / "questions" / "lineage.jsonl"
TOKENS_IN, TOKENS_OUT = 100, 10


def answer(asked):
    records = map(json.loads, KEY.read_text().splitlines())
    question = next(record for record in records if record["id"] == asked["id"])
    if question["tier"] != 1:
        return {"answer": "not in the record", "answer_ids": [], "abstained": True}
    return {"answer": ", ".join(question["answer_names"]), "answer_ids": question["answer"],
            "abstained": False}


def main():
    """`stubbed` is the marker a canned arm owes the scoreboard. This arm is canned, so it says
    so on every question, and the demo's own leg reads as the non measurement it is."""
    asked = json.loads(sys.stdin.read())
    print(json.dumps({**answer(asked), "tokens_in": TOKENS_IN, "tokens_out": TOKENS_OUT,
                      "stubbed": True, "cost_usd": 0.0, "seconds": 0.0,
                      "chunks": [], "path": []}))


if __name__ == "__main__":
    main()
