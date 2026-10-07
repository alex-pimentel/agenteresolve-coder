#!/usr/bin/env bash
set -euo pipefail
root="${1:-/tmp/agenteresolve-seed}"
rm -rf "$root"
mkdir -p "$root/remotes"
git init --bare -q "$root/remotes/demo.git"
git init -q "$root/work"
cd "$root/work"
git config user.email seed@local
git config user.name seed
printf 'hello\n' > README.md
git add README.md
git commit -qm 'chore: seed'
git remote add origin "$root/remotes/demo.git"
git push -q origin HEAD:main
echo "$root"
