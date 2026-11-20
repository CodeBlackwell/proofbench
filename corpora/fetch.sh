#!/usr/bin/env bash
# Clone every `ready` entry in manifest.yaml into ./repos, materializing a local
# default branch and answer branch, each at its pinned commit, with the broken default
# checked out. Re-runnable. Cloned repos are gitignored; only the manifest is tracked.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
mkdir -p repos

python3 - <<'PY' | while IFS='|' read -r name url def ans pin answer_pin; do
import yaml
for e in yaml.safe_load(open("manifest.yaml"))["ready"]:
    print("|".join(e[key] for key in ("name", "url", "default_branch", "answer_branch", "pin", "answer_pin")))
PY
  repo="repos/$name"
  [ -d "$repo/.git" ] || git clone -q "$url" "$repo"
  git -C "$repo" fetch -q origin
  git -C "$repo" checkout -q --detach
  git -C "$repo" branch -f "$def" "$pin"
  git -C "$repo" branch -f "$ans" "$answer_pin"
  git -C "$repo" checkout -q "$def"
  echo "fetched $name (default: $def @ ${pin:0:7}, answer: $ans @ ${answer_pin:0:7})"
done
