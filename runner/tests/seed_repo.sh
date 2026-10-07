#!/usr/bin/env bash
set -euo pipefail
root="${1:-./runner/tests/remotes}"
mkdir -p "$root"
root="$(cd "$root" && pwd)"
rm -rf "$root/demo.git" "$root/work"
git init --bare -q "$root/demo.git"
git init -q "$root/work"
git -C "$root/work" config user.email seed@local
git -C "$root/work" config user.name seed
printf 'hello\n' > "$root/work/README.md"
git -C "$root/work" add README.md
git -C "$root/work" commit -qm 'chore: seed'
git -C "$root/work" remote add origin "$root/demo.git"
git -C "$root/work" push -q origin HEAD:main
echo "$root"
