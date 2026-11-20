"""Rebuild the two hard, benchmark-derived corpus cases as buggy->fixed git pairs.

Each case is one published-benchmark instance materialized locally (repos/ is gitignored):
  pdb-multi-shortest-substring  PDB-Multi 3692_41 (arXiv 2604.17338) — 3 bugs, complete GT.
  repodebug-gvl-tracing         RepoDebug (EMNLP 2025) C wrong_return; upstream = fixed ref.

Run:  python3 corpora/build_hard.py
"""
import json
import subprocess
import urllib.request
from pathlib import Path

REPOS = Path(__file__).resolve().parent / "repos"
PDB = "https://datasets-server.huggingface.co/rows?dataset=Precise-Debugging-Benchmarking%2FPDB-Multi&config=default&split=test&offset={off}&length=100"
RD = "https://raw.githubusercontent.com/BUAA-IRIP-LLM/RepoDebug/main/data/c.json"


def _get(url):
    return urllib.request.urlopen(url, timeout=30).read().decode("utf-8", "replace")


def _git(repo, *args):
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")


def build(name, fname, buggy, fixed, readme):
    repo = REPOS / name
    subprocess.run(["rm", "-rf", str(repo)], check=True)
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "buggy")
    _git(repo, "config", "user.email", "corpus@proofbench.local")
    _git(repo, "config", "user.name", "proofbench corpus")
    (repo / "README.md").write_text(readme)
    (repo / fname).write_text(buggy)
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "buggy baseline")
    _git(repo, "checkout", "-q", "-b", "fixed")
    (repo / fname).write_text(fixed)
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "fixed")
    _git(repo, "checkout", "-q", "buggy")
    print(f"built {name}")


def pdb_instance(task_id="3692_41"):
    for off in (0, 100, 200):
        for row in json.loads(_get(PDB.format(off=off)))["rows"]:
            if row["row"]["task_id"] == task_id:
                return row["row"]
    raise SystemExit(f"PDB task {task_id} not found")


def repodebug_instance(repo_name="ivoanjo/gvl-tracing", error_type="wrong_return"):
    for r in json.loads(_get(RD)):
        if r["repo_name"] == repo_name and r["error_type"] == error_type:
            return r
    raise SystemExit("RepoDebug instance not found")


def apply_perturbation(upstream, diff):
    """RepoDebug diff is original->buggy; '-' lines (originals) must exist in upstream."""
    lines = [l for l in diff.splitlines() if not l.startswith(("--- ", "+++ "))]  # file headers
    rem = "\n".join(l[1:] for l in lines if l[:1] == "-")
    add = "\n".join(l[1:] for l in lines if l[:1] == "+")
    if rem not in upstream:
        raise SystemExit("upstream drifted: perturbation no longer applies")
    return upstream.replace(rem, add, 1)


def main():
    p = pdb_instance()
    build("pdb-multi-shortest-substring", "solution.py",
          p["buggy_code"].rstrip() + "\n", p["gt_solution"].rstrip() + "\n",
          "# shortest-matching-substring\n\nReconstructed from PDB-Multi "
          f"({p['task_id']}, {p['bug_count']} injected bugs).\n\n## Spec\n\n"
          + p["task_prompt"].strip() + "\n")

    r = repodebug_instance()
    upstream = _get(f"https://raw.githubusercontent.com/{r['repo_name']}/HEAD/{r['file_path']}")
    build("repodebug-gvl-tracing", r["file_path"].split("/")[-1],
          apply_perturbation(upstream, r["diff"]), upstream,
          "# gvl-tracing (native extension excerpt)\n\nOne file from `ivoanjo/gvl-tracing` "
          "(RepoDebug, EMNLP 2025). Exactly one functional bug was injected.\n")


if __name__ == "__main__":
    main()
