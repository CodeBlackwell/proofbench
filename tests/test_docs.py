"""The docs point at each other and at files in the repo, and a link that lands nowhere is a
wrong statement. One page once told readers to run a config file that did not exist."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKIPPED = {".venv", "runs", "repos", "dist", "node_modules", ".pytest_cache"}
PAGES = sorted(page for page in ROOT.rglob("*.md")
               if not SKIPPED & set(page.relative_to(ROOT).parts))
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)


def read_prose(page):
    """The page without its fenced code, where a bracket is code and a # is a comment."""
    return FENCE.sub("", page.read_text())


def find_anchors(page):
    """The anchor GitHub gives each heading: lower case, punctuation dropped, spaces to
    hyphens, and -1, -2 added to a heading that repeats."""
    anchors, seen = set(), {}
    for line in read_prose(page).splitlines():
        if line.startswith("#"):
            slug = re.sub(r"[^\w\- ]", "", line.lstrip("#").strip().lower()).replace(" ", "-")
            anchors.add(f"{slug}-{seen[slug]}" if slug in seen else slug)
            seen[slug] = seen.get(slug, 0) + 1
    return anchors


@pytest.mark.parametrize("page", PAGES, ids=lambda page: str(page.relative_to(ROOT)))
def test_every_link_in_the_page_lands(page):
    for target in LINK.findall(read_prose(page)):
        if re.match(r"[a-z]+:", target):
            continue    # http and mailto are not ours to check offline
        path, _, anchor = target.partition("#")
        landing = (page.parent / path).resolve() if path else page
        assert landing.exists(), f"{target} points at nothing"
        # A Mac's disk forgives the wrong case in a file name. GitHub does not.
        assert landing.name in {one.name for one in landing.parent.iterdir()}, \
            f"{target} has the wrong case for {landing.parent.name}/"
        if anchor and landing.suffix == ".md":
            assert anchor in find_anchors(landing), f"{target} names no heading in {landing.name}"


def test_every_reference_page_is_listed_in_the_index():
    index = (ROOT / "docs" / "README.md").read_text()
    for page in (ROOT / "docs").glob("*.md"):
        assert page.name == "README.md" or f"({page.name})" in index, f"{page.name} is not indexed"
