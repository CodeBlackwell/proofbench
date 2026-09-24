#!/usr/bin/env python3
"""A stub arm, for the demo and the tests only. It measures nothing.

It reads the question's own answer key, which a real arm never sees, answers tier 1 from it
and abstains everywhere else, so the fixture grades to known accuracy and abstention numbers
offline: no API key, no network, no `claude` CLI."""
import json
import sys

TOKENS_IN, TOKENS_OUT = 100, 10


def answer(question):
    if question["tier"] != 1:
        return {"answer": "not in the record", "answer_ids": [], "abstained": True}
    return {"answer": ", ".join(question["answer_names"]), "answer_ids": question["answer"],
            "abstained": False}


def main():
    """`stubbed` is the marker a canned arm owes the scoreboard. This arm is canned, so it says
    so on every question, and the demo's own leg reads as the non measurement it is."""
    question = json.loads(sys.stdin.read())
    print(json.dumps({**answer(question), "tokens_in": TOKENS_IN, "tokens_out": TOKENS_OUT,
                      "stubbed": True, "cost_usd": 0.0, "seconds": 0.0,
                      "chunks": [], "path": []}))


if __name__ == "__main__":
    main()
