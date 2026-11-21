"""The objective: the one number the optimize gate compares, and the names it may have."""
import re

from .util import die

# pass^3, pass@3, and the names an abstention only leg carries them under.
PASS_OBJECTIVE = re.compile(r"(?:abstention_)?pass[@^](\d+)")
# The other numbers on a question leg whose better direction the optimize gate knows.
QUESTION_OBJECTIVES = {"accuracy", "abstention_rate", "abstention_correct_unanswerable",
                       "tokens_per_correct", "tokens_per_correct_abstention"}


def _refuse_beyond_trials(objective, trials):
    """pass^k and pass@k exist only for k up to the trials run. An objective naming a larger k
    is refused here, before the run is spent, and not after it by a missing scoreboard key."""
    asked = PASS_OBJECTIVE.fullmatch(objective)
    if asked and int(asked.group(1)) > trials:
        die(f"objective '{objective}' needs {asked.group(1)} trials, and the config runs {trials}")


def read(raw, kind, trials, repo_default):
    """The number the optimize gate compares. A repo leg's numbers are whatever the judge
    returns, macro averaged. A question leg's are fixed, and only the ones whose better
    direction is known are taken: the gate would have kept a rewrite for a higher token count.
    A question corpus that only runs may leave it out. A repo corpus that leaves it out is
    compared on the number its grader returns."""
    objective = raw.get("objective", repo_default if kind == "repo" else None)
    if objective is None:
        return None
    known = str(objective).startswith("macro_") if kind == "repo" else (
        objective in QUESTION_OBJECTIVES or PASS_OBJECTIVE.fullmatch(str(objective)))
    if not known:
        die(f"objective '{objective}' is not a number a {kind} leg's gate can compare")
    _refuse_beyond_trials(objective, trials)
    return objective
