"""git-diff capture: reset a repo to its broken state, then snapshot what the agent changed.

The dominant agent-eval case is "agent edits a repo, grade the diff against an answer
branch." Dependency and cache trees are excluded: they are never the agent's fix and can
balloon the judge prompt past ARG_MAX."""
import subprocess

_EXCLUDES = [":(exclude,glob)**/node_modules/**", ":(exclude,glob)**/.venv/**",
             ":(exclude,glob)**/__pycache__/**", ":(exclude,glob)**/.code-review-graph/**"]


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)


def reset(repo, default_branch):
    """Restore the repo to a pristine broken state. --detach tolerates the branch being
    checked out in another worktree."""
    _git(repo, "checkout", "-q", "--detach", default_branch)
    _git(repo, "reset", "-q", "--hard")
    _git(repo, "clean", "-qfdx")


def ground_truth(repo, default_branch, answer_branch):
    return _git(repo, "diff", f"{default_branch}..{answer_branch}").stdout


def capture(repo, baseline):
    """Diff against the buggy baseline ref, not the working tree: agents may commit their
    fixes. reset() detaches HEAD, so the baseline ref stays pinned while agent commits move
    HEAD, and this diff captures the fix whether it was committed or left uncommitted."""
    _git(repo, "add", "-N", ".")
    return _git(repo, "diff", baseline, "--", ".", *_EXCLUDES).stdout
