"""git-diff capture: clone a repo at its broken state, then snapshot what the agent changed.

The dominant agent-eval case is "agent edits a repo, grade the diff against an answer
branch." The corpus repo is only ever read. The agent works in a throwaway clone that holds
the broken branch alone, so the answer is not in it and nothing the agent does outlives the
attempt. Dependency and cache trees are excluded from the diff: they are never the agent's fix
and can balloon the judge prompt past ARG_MAX."""
import os
from pathlib import Path

from .util import die, spawn

# What one agent's tools leave behind is that corpus's business: it goes in the task's `ignore`.
_EXCLUDES = [":(exclude,glob)**/node_modules/**", ":(exclude,glob)**/.venv/**",
             ":(exclude,glob)**/__pycache__/**"]


def _git(repo, *args):
    """Every call here decides what gets graded, so a git failure is fatal. Read as empty
    output it would become an empty answer key or an agent that seemed to change nothing."""
    proc = spawn(["git", "-C", str(repo), *args])
    if proc.returncode != 0:
        die(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")
    return proc.stdout


def pin(repo, ref):
    return _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def _leave_out(patterns):
    return [f":(exclude,glob){pattern}" for pattern in patterns]


def ground_truth(repo, default_branch, answer_branch, ignore=()):
    """The baseline commit and the answer diff, both read once before any agent runs. The
    baseline travels as a commit and never as a branch name, because an agent can move a
    branch. A path inside some other repo is refused: git would answer for that outer repo.
    A task's ignored paths are left out, here and in capture, so neither side is graded on
    them."""
    if not Path(_git(repo, "rev-parse", "--show-toplevel").strip()).samefile(repo):
        die(f"{repo} is not the root of a git repository")
    baseline = pin(repo, default_branch)
    answer = _git(repo, "diff", baseline, pin(repo, answer_branch), "--", ".",
                  *_leave_out(ignore))
    return baseline, answer or die(
        f"{answer_branch} changes nothing against {default_branch} in {repo}: no ground truth")


def workspace(repo, default_branch, baseline, dest):
    """A fresh clone of the default branch alone, detached at the baseline. --no-local copies
    only the objects that branch reaches, and the remote is dropped, so the clone holds neither
    the answer nor a way to fetch it."""
    _git(repo, "clone", "-q", "--no-local", "--single-branch", "--branch", default_branch,
         ".", str(dest))
    _git(dest, "checkout", "-q", "--detach", baseline)
    _git(dest, "remote", "remove", "origin")
    return dest


_IGNORE_FILES = ":(glob)**/.gitignore"
# The launching user's global ignore file is left out too: a diff must not depend on whose
# machine took it, and a config setting is one more place an agent can name an ignore file.
_ADD = ("-c", f"core.excludesFile={os.devnull}", "add", "--intent-to-add")


def _names(listing):
    return [name for name in listing.split("\0") if name]


def _restore_baseline_ignore_rules(repo, baseline):
    """Put git's ignore rules back as the baseline had them, and return where the agent's own
    .gitignore files were set aside: every one it created, changed or deleted."""
    changed = _git(repo, "diff", "--name-only", "-z", baseline, "--", _IGNORE_FILES)
    created = _git(repo, "ls-files", "--others", "-z", "--", _IGNORE_FILES)
    touched = sorted(set(_names(changed + created)))
    aside = repo / ".git" / "proofbench-set-aside"
    aside.mkdir(exist_ok=True)
    for number, name in enumerate(touched):
        if os.path.lexists(repo / name):
            (repo / name).rename(aside / str(number))
    listed = _git(repo, "ls-tree", "-r", "--name-only", "-z", baseline, "--", *touched) if touched else ""
    if _names(listed):
        _git(repo, "checkout", "-q", baseline, "--", *_names(listed))
    (repo / ".git" / "info" / "exclude").unlink(missing_ok=True)
    return touched, aside


def _put_back(repo, touched, aside):
    """The agent's .gitignore files, as it left them: its changes to them are part of its diff."""
    for number, name in enumerate(touched):
        (repo / name).unlink(missing_ok=True)
        if os.path.lexists(aside / str(number)):
            (aside / str(number)).rename(repo / name)
    kept = [name for name in touched if os.path.lexists(repo / name)]
    if kept:
        _git(repo, *_ADD, "--force", "--", *kept)


def _clear_index_flags(repo):
    """assume-unchanged and skip-worktree tell git to stop looking at a file, so an edit made
    after setting one never reaches a diff. `ls-files -v` marks the first with a lower case
    tag and the second with S. Each is cleared in its own call: given both options at once,
    git acts on only one of them."""
    tagged = _names(_git(repo, "ls-files", "-v", "-z"))
    flagged = [entry[2:] for entry in tagged if entry[0].islower() or entry[0] == "S"]
    for clear in ("--no-assume-unchanged", "--no-skip-worktree") if flagged else ():
        _git(repo, "update-index", clear, "--", *flagged)


def capture(repo, baseline, ignore=()):
    """Diff against the baseline commit, not the working tree: agents may commit their fixes,
    on a detached HEAD or on the branch itself, and the commit id is the one ref they cannot
    move. New files are put in the diff by `git add`, which skips what git is told to ignore,
    so they are added under the baseline's ignore rules: an agent that wrote its own would
    otherwise decide which of its files get graded. For the same reason the index flags that
    make git stop looking at a file are cleared first."""
    _clear_index_flags(repo)
    touched, aside = _restore_baseline_ignore_rules(repo, baseline)
    _git(repo, *_ADD, ".")
    _put_back(repo, touched, aside)
    return _git(repo, "diff", baseline, "--", ".", *_EXCLUDES, *_leave_out(ignore))
