"""git-diff capture: clone a repo at its broken state, then snapshot what the agent changed.

The dominant agent-eval case is "agent edits a repo, grade the diff against an answer
branch." The corpus repo is only ever read. The agent works in a throwaway clone that holds
the broken branch alone, so the answer is not in it and nothing the agent does outlives the
attempt. Dependency and cache trees are excluded from the diff: they are never the agent's fix
and can balloon the judge prompt past ARG_MAX."""
from pathlib import Path

from .util import die, spawn

_EXCLUDES = [":(exclude,glob)**/node_modules/**", ":(exclude,glob)**/.venv/**",
             ":(exclude,glob)**/__pycache__/**", ":(exclude,glob)**/.code-review-graph/**"]

# Multi-assistant MCP scaffolding that `code-review-graph build` scatters at the repo root to
# advertise its tools. It is deterministic tool scratch, never an agent fix, so it must not
# count against precision when grading a graph-driven debugger.
_EXCLUDES += [f":(exclude,glob){p}" for p in (
    ".mcp.json", ".opencode.json", ".cursorrules", ".windsurfrules",
    "AGENTS.md", "CLAUDE.md", "GEMINI.md", "QODER.md",
    ".claude/**", ".cursor/**", ".gemini/**", ".kiro/**", ".qoder/**")]


def _git(repo, *args):
    """Every call here decides what gets graded, so a git failure is fatal. Read as empty
    output it would become an empty answer key or an agent that seemed to change nothing."""
    proc = spawn(["git", "-C", str(repo), *args])
    if proc.returncode != 0:
        die(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")
    return proc.stdout


def _pin(repo, ref):
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
    baseline = _pin(repo, default_branch)
    answer = _git(repo, "diff", baseline, _pin(repo, answer_branch), "--", ".",
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


def capture(repo, baseline, ignore=()):
    """Diff against the baseline commit, not the working tree: agents may commit their fixes,
    on a detached HEAD or on the branch itself, and the commit id is the one ref they cannot
    move. add -N puts new files in the diff."""
    _git(repo, "add", "-N", ".")
    return _git(repo, "diff", baseline, "--", ".", *_EXCLUDES, *_leave_out(ignore))
