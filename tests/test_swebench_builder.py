"""The SWE-bench builder, offline: the dataset is stubbed and the upstream project is a local
repo, so what is tested is that the pinned commit and the pinned patch land on the right
branches, and that proofbench can take its ground truth and its clone from the result."""
import hashlib
import importlib.util
import io
import re
from pathlib import Path

import pytest
import yaml

from proofbench import capture

from .conftest import git

CORPORA = Path(__file__).resolve().parent.parent / "corpora"
MANIFEST = yaml.safe_load((CORPORA / "manifest.yaml").read_text())


@pytest.fixture
def swe(repo, tmp_path, monkeypatch):
    """The builder, pointed at the `repo` fixture as its upstream project and at a dataset of
    one instance whose gold patch is that repo's own fix."""
    spec = importlib.util.spec_from_file_location("build_swebench", CORPORA / "build_swebench.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    patch = git(repo, "diff", "buggy", "fixed") + "\n"
    row = {"repo": "owner/project", "base_commit": git(repo, "rev-parse", "buggy"),
           "patch": patch, "problem_statement": "x should be 2.\n"}
    upstream = repo.parent / "owner" / "project"
    upstream.parent.mkdir()
    repo.rename(upstream)
    monkeypatch.setattr(module, "REPOS", tmp_path / "repos")
    monkeypatch.setattr(module, "UPSTREAM", str(repo.parent / "{repo}"))
    monkeypatch.setattr(module, "row", lambda name: row)
    return module


def pinned(swe, name):
    row = swe.row(name)
    return {"name": name, "repo": row["repo"], "base": row["base_commit"],
            "patch_sha256": hashlib.sha256(row["patch"].encode()).hexdigest()}


def test_an_instance_becomes_a_base_branch_and_a_fixed_branch(swe, tmp_path):
    swe.build(pinned(swe, "one"))
    built = tmp_path / "repos" / "owner__project"
    assert git(built, "show", "one:README") == "x should be 2."
    assert git(built, "show", "one:a.py") == "x = 1"
    assert git(built, "diff", "--name-only", "one", "one-fixed") == "a.py"


def test_proofbench_can_grade_from_what_was_built(swe, tmp_path):
    """The built repo is shallow, and every attempt is a clone of it."""
    swe.build(pinned(swe, "one"))
    built = tmp_path / "repos" / "owner__project"
    baseline, answer = capture.ground_truth(built, "one", "one-fixed")
    assert "+x = 2" in answer and "README" not in answer
    work = capture.workspace(built, "one", baseline, tmp_path / "work")
    assert (work / "README").read_text() == "x should be 2.\n"


def test_instances_of_one_project_share_a_repo(swe, tmp_path):
    swe.build(pinned(swe, "one"))
    swe.build(pinned(swe, "two"))
    assert [path.name for path in (tmp_path / "repos").iterdir()] == ["owner__project"]
    branches = git(tmp_path / "repos" / "owner__project", "branch", "--format=%(refname:short)")
    assert sorted(branches.split()) == ["one", "one-fixed", "two", "two-fixed"]


def test_a_gold_patch_that_has_changed_is_refused(swe):
    with pytest.raises(SystemExit, match="pinned hash"):
        swe.build({**pinned(swe, "one"), "patch_sha256": "0" * 64})


def test_an_instance_nobody_pinned_is_refused(swe):
    with pytest.raises(SystemExit, match="no-such-instance"):
        swe.main(["no-such-instance"])


@pytest.mark.parametrize("case", MANIFEST["swebench"], ids=lambda case: case["name"])
def test_a_swebench_instance_is_pinned_on_both_sides(case):
    assert re.fullmatch(r"[0-9a-f]{40}", case["base"]), f"{case['name']} base is not a commit id"
    assert re.fullmatch(r"[0-9a-f]{64}", case["patch_sha256"])
    assert case["name"].startswith(case["repo"].replace("/", "__") + "-")


def test_a_dataset_server_that_fails_once_is_asked_again(swe, monkeypatch):
    replies = iter([OSError("HTTP Error 502: Bad Gateway"), io.BytesIO(b'{"rows": []}')])

    def answer(url, timeout):
        reply = next(replies)
        if isinstance(reply, OSError):
            raise reply
        return reply
    monkeypatch.setattr(swe.urllib.request, "urlopen", answer)
    monkeypatch.setattr(swe.time, "sleep", lambda seconds: None)
    assert swe._fetch("https://dataset.invalid/filter") == b'{"rows": []}'
