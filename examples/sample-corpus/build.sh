#!/usr/bin/env bash
# Build the bundled demo corpus: two tiny MIT-licensed repos, each with a `buggy`
# default branch and a `fixed` answer branch. Generated into ./repos (gitignored) so
# the parent repo stays free of nested .git dirs. Re-runnable; wipes ./repos first.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HERE/repos"
rm -rf "$DEST"; mkdir -p "$DEST"

make_repo() { # make_repo <name> <buggy_file> <fixed_file> <readme>
  local name="$1" repo="$DEST/$1"
  git -c init.defaultBranch=buggy init -q "$repo"
  git -C "$repo" config user.email demo@proofbench.local
  git -C "$repo" config user.name proofbench-demo
  printf '%s' "$4" > "$repo/README.md"
  printf '%s' "$2" > "$repo/lib.py"
  git -C "$repo" add -A && git -C "$repo" commit -qm "initial"
  git -C "$repo" checkout -q -b fixed
  printf '%s' "$3" > "$repo/lib.py"
  git -C "$repo" commit -qam "fix"
  git -C "$repo" checkout -q buggy
  echo "built $name (buggy + fixed)"
}

make_repo primes \
'def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return True
    return True
' \
'def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True
' \
'# primes

`is_prime(n)` returns True if and only if `n` is a prime number.
'

make_repo ranges \
'def count_up(n):
    """Return the list [1, 2, ..., n]."""
    return list(range(1, n))
' \
'def count_up(n):
    """Return the list [1, 2, ..., n]."""
    return list(range(1, n + 1))
' \
'# ranges

`count_up(n)` returns the list of integers from 1 to n inclusive.
'
