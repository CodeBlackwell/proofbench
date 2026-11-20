"""The scripts that build the real corpus. Everything here is offline: the network is stubbed,
so what is tested is that the right commit lands on the right branch and that the corpus config
names no task the scripts cannot build."""
import importlib.util
import re
from pathlib import Path

import pytest
import yaml

from .conftest import git

CORPORA = Path(__file__).resolve().parent.parent / "corpora"
MANIFEST = yaml.safe_load((CORPORA / "manifest.yaml").read_text())
CASE = {"name": "one-file-fix", "repo": "owner/project", "file": "src/deep/module.c",
        "parent": "a" * 40, "fix": "b" * 40, "readme": "# What the module must do\n"}


@pytest.fixture
def build_hard(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("build_hard", CORPORA / "build_hard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "REPOS", tmp_path)
    monkeypatch.setattr(module, "_get", lambda url: f"the file as fetched from {url}\n")
    return module


def test_an_upstream_case_puts_the_parent_on_buggy_and_the_fix_on_fixed(build_hard, tmp_path):
    build_hard.build_upstream(CASE)
    repo = tmp_path / "one-file-fix"
    raw = "https://raw.githubusercontent.com/owner/project/{}/src/deep/module.c"
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "buggy"
    assert git(repo, "show", "buggy:src/deep/module.c") == f"the file as fetched from {raw.format('a' * 40)}"
    assert git(repo, "show", "fixed:src/deep/module.c") == f"the file as fetched from {raw.format('b' * 40)}"
    assert git(repo, "show", "buggy:README.md") == "# What the module must do"
    assert git(repo, "diff", "--name-only", "buggy", "fixed") == "src/deep/module.c"


def test_only_the_cases_asked_for_are_built(build_hard, tmp_path, monkeypatch):
    monkeypatch.setattr(build_hard, "upstream_cases", lambda: [CASE, {**CASE, "name": "another"}])
    build_hard.main(["another"])
    assert [path.name for path in tmp_path.iterdir()] == ["another"]


def test_a_case_nobody_can_build_is_refused(build_hard):
    with pytest.raises(SystemExit, match="no-such-case"):
        build_hard.main(["no-such-case"])


@pytest.mark.parametrize("case", MANIFEST["upstream"], ids=lambda case: case["name"])
def test_an_upstream_case_is_pinned_to_whole_commit_ids(case):
    """A short id or a branch name would let the ground truth move under the corpus."""
    for side in ("parent", "fix"):
        assert re.fullmatch(r"[0-9a-f]{40}", case[side]), f"{case['name']} {side} is not a commit id"
    assert case["readme"].strip() and case["file"] and "/" in case["repo"]


def test_every_task_in_the_corpus_config_can_be_built(build_hard):
    config = yaml.safe_load((CORPORA / "proofbench.yaml").read_text())
    buildable = ({entry["name"] for entry in MANIFEST["ready"]} | set(build_hard.BENCHMARKS)
                 | {case["name"] for case in MANIFEST["upstream"]})
    assert {task["name"] for task in config["corpus"]} <= buildable
