"""Source for stub arms. The harness hands an arm a question's id and text only, so a stub that
answers from the answer key has to open the key file itself, as the demo oracle does."""


def read_question_from(key_file):
    """Arm source that binds `question` to the full record of the question asked on stdin."""
    return ("import json, sys\n"
            f"records = map(json.loads, open({str(key_file)!r}).read().splitlines())\n"
            "asked = json.loads(sys.stdin.read())\n"
            "question = next(record for record in records if record['id'] == asked['id'])\n")
