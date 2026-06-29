#!/usr/bin/env bash
# Clone every `ready` entry in manifest.yaml into ./repos, materializing a local
# default branch (at the pinned commit) and answer branch, with the broken default
# checked out. Re-runnable. Cloned repos are gitignored; only the manifest is tracked.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
mkdir -p repos

python3 - <<'PY' | while IFS='|' read -r name url def ans pin; do
import yaml
for e in yaml.safe_load(open("manifest.yaml"))["ready"]:
    print(f"{e['name']}|{e['url']}|{e['default_branch']}|{e['answer_branch']}|{e['pin']}")
PY
  repo="repos/$name"
  [ -d "$repo/.git" ] || git clone -q "$url" "$repo"
  git -C "$repo" fetch -q origin
  git -C "$repo" checkout -q --detach
  git -C "$repo" branch -f "$def" "$pin"
  git -C "$repo" branch -f "$ans" "origin/$ans"
  git -C "$repo" checkout -q "$def"
  echo "fetched $name @ ${pin:0:7} (default: $def, answer: $ans)"
done
