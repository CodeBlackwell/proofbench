"""Build the hard corpus cases as buggy->fixed git pairs under repos/ (gitignored).

Two come from published benchmarks, one instance each:
  pdb-multi-shortest-substring  PDB-Multi 3692_41 (arXiv 2604.17338) — 3 bugs, complete GT.
  repodebug-gvl-tracing         RepoDebug (EMNLP 2025) C wrong_return; upstream = fixed ref.

Three are real upstream fixes, listed under `upstream` in manifest.yaml and pinned there to the
fix commit and its parent: cpython-timsort, cpython-asyncio-cond, sudo-baron-samedit.

Run:  uv run python corpora/build_hard.py            every case
      uv run python corpora/build_hard.py NAME ...   only the cases named
"""
import json
import subprocess
import sys
import urllib.request
from functools import partial
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPOS = HERE / "repos"
PDB = "https://datasets-server.huggingface.co/rows?dataset=Precise-Debugging-Benchmarking%2FPDB-Multi&config=default&split=test&offset={off}&length=100"
RD = "https://raw.githubusercontent.com/BUAA-IRIP-LLM/RepoDebug/main/data/c.json"
RAW = "https://raw.githubusercontent.com/{repo}/{commit}/{file}"


def _get(url):
    return urllib.request.urlopen(url, timeout=30).read().decode("utf-8", "replace")


def _git(repo, *args):
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")


def build(name, fname, buggy, fixed, readme):
    repo = REPOS / name
    subprocess.run(["rm", "-rf", str(repo)], check=True)
    (repo / fname).parent.mkdir(parents=True)
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


def build_pdb():
    p = pdb_instance()
    build("pdb-multi-shortest-substring", "solution.py",
          p["buggy_code"].rstrip() + "\n", p["gt_solution"].rstrip() + "\n",
          "# shortest-matching-substring\n\nReconstructed from PDB-Multi "
          f"({p['task_id']}, {p['bug_count']} injected bugs).\n\n## Spec\n\n"
          + p["task_prompt"].strip() + "\n")


def build_repodebug():
    r = repodebug_instance()
    upstream = _get(f"https://raw.githubusercontent.com/{r['repo_name']}/HEAD/{r['file_path']}")
    build("repodebug-gvl-tracing", r["file_path"].split("/")[-1],
          apply_perturbation(upstream, r["diff"]), upstream,
          "# gvl-tracing (native extension excerpt)\n\nOne file from `ivoanjo/gvl-tracing` "
          "(RepoDebug, EMNLP 2025). Exactly one functional bug was injected.\n")


BENCHMARKS = {"pdb-multi-shortest-substring": build_pdb, "repodebug-gvl-tracing": build_repodebug}


def upstream_cases():
    return yaml.safe_load((HERE / "manifest.yaml").read_text())["upstream"]


def build_upstream(case):
    """One file of a real project, as it stood just before a fix and just after it. Both
    commits are pinned in the manifest, so the ground truth cannot move with upstream."""
    at = partial(RAW.format, repo=case["repo"], file=case["file"])
    build(case["name"], case["file"], _get(at(commit=case["parent"])),
          _get(at(commit=case["fix"])), case["readme"])


def main(wanted):
    builders = {**BENCHMARKS,
                **{case["name"]: partial(build_upstream, case) for case in upstream_cases()}}
    unknown = sorted(set(wanted) - set(builders))
    if unknown:
        raise SystemExit(f"no such case: {unknown}; known: {sorted(builders)}")
    for name in wanted or builders:
        builders[name]()


if __name__ == "__main__":
    main(sys.argv[1:])
