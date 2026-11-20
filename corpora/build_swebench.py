"""Build SWE-bench Verified instances as buggy->fixed branch pairs under repos/ (gitignored).

Each instance listed under `swebench` in manifest.yaml becomes two branches of one repo per
upstream project: `<name>` is the base commit with the issue text as README, `<name>-fixed`
adds the gold patch. The base commit and the gold patch's hash are pinned in the manifest.

Run:  uv run python corpora/build_swebench.py              every pinned instance
      uv run python corpora/build_swebench.py NAME ...     only the instances named
      uv run python corpora/build_swebench.py --pin NAME   print manifest entries to paste
"""
import hashlib
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPOS = HERE / "repos"
FILTER = "https://datasets-server.huggingface.co/filter"
DATASET = {"dataset": "princeton-nlp/SWE-bench_Verified", "config": "default", "split": "test"}
UPSTREAM = "https://github.com/{repo}"


def _git(repo, *args, stdin=None):
    proc = subprocess.run(["git", "-C", str(repo), *args], input=stdin, capture_output=True,
                          text=True)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")


def _fetch(url, waits=(10, 30)):
    """The dataset server answered 502, 429 and nothing at all within a dozen requests while
    this was written, so one failure is not taken as its last word."""
    for wait in waits:
        try:
            return urllib.request.urlopen(url, timeout=60).read()
        except OSError as failure:
            print(f"dataset server: {failure}; trying again in {wait}s", file=sys.stderr)
            time.sleep(wait)
    return urllib.request.urlopen(url, timeout=60).read()


def row(name):
    """One instance of the benchmark, asked for on its own: the whole set is megabytes a page,
    and the server turns away a client that keeps asking for all of it."""
    query = urllib.parse.urlencode({**DATASET, "where": f"\"instance_id\"='{name}'", "length": 1})
    found = json.loads(_fetch(f"{FILTER}?{query}"))["rows"]
    if not found:
        raise SystemExit(f"SWE-bench Verified has no instance {name}")
    return found[0]["row"]


def _hash(patch):
    return hashlib.sha256(patch.encode()).hexdigest()


def _project(name):
    """The one repo every instance of an upstream project shares, so 200 django instances are
    not 200 copies of django."""
    repo = REPOS / name.replace("/", "__")
    if not (repo / ".git").exists():
        repo.mkdir(parents=True)
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "corpus@proofbench.local")
        _git(repo, "config", "user.name", "proofbench corpus")
    return repo


def build(case):
    instance = row(case["name"])
    if _hash(instance["patch"]) != case["patch_sha256"]:
        raise SystemExit(f"{case['name']}: the gold patch no longer matches its pinned hash")
    repo = _project(case["repo"])
    _git(repo, "fetch", "-q", "--depth", "1", UPSTREAM.format(repo=case["repo"]), case["base"])
    _git(repo, "checkout", "-q", "-f", "-B", case["name"], "FETCH_HEAD")
    # A bare README sorts first among a project's readme files, so it is the one the judge is
    # shown, and no patch written against upstream touches it.
    (repo / "README").write_text(instance["problem_statement"])
    _git(repo, "add", "--force", "README")
    _git(repo, "commit", "-q", "-m", "task statement")
    _git(repo, "checkout", "-q", "-B", f"{case['name']}-fixed")
    _git(repo, "apply", "--index", "-", stdin=instance["patch"])
    _git(repo, "commit", "-q", "-m", "gold patch")
    print(f"built {case['name']}")


def pin(names):
    for name in names:
        instance = row(name)
        print(f"  - {{name: {name}, repo: {instance['repo']}, base: {instance['base_commit']}, "
              f"patch_sha256: {_hash(instance['patch'])}}}")


def main(wanted):
    if wanted[:1] == ["--pin"]:
        return pin(wanted[1:])
    cases = {case["name"]: case
             for case in yaml.safe_load((HERE / "manifest.yaml").read_text())["swebench"]}
    unknown = sorted(set(wanted) - set(cases))
    if unknown:
        raise SystemExit(f"not pinned in the manifest: {unknown}")
    for name in wanted or cases:
        build(cases[name])


if __name__ == "__main__":
    main(sys.argv[1:])
