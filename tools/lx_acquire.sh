#!/usr/bin/env bash
# tools/lx_acquire.sh — BT-LX-01 (LINUX_DISTILL §3.4). A3 (SPDX) is recorded, not blocking, until the operator's exemption list exists.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SHA=549531755d329ec48439e3263535351ba1c5acd5
TREE=e56d24e86147e65a8ade3cfe69dee2bfdac279fa
D="${LX_PIN_DIR:-$ROOT/rcu-free-v3@5495317}"
test ! -e "$D" || { echo "E_LX_EXISTS $D"; exit 9; }
mkdir -p "$D/src" "$D/meta" && cd "$D/src"
git init -q && git remote add origin https://github.com/torvalds/linux.git
git sparse-checkout init --no-cone
git sparse-checkout set --no-cone --stdin < "$ROOT/spec/SPARSE.patterns"
diff -q <(git sparse-checkout list | grep -v '^#' | sed '/^$/d') \
        <(grep -v '^#' "$ROOT/spec/SPARSE.patterns" | sed '/^$/d') \
  || { echo "E_LX_A0 patterns not applied verbatim"; exit 2; }
echo "A0 ok"
git fetch --depth 1 --filter=blob:none --no-tags origin "$SHA"
git checkout -q --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$SHA"            || { echo E_LX_A1_COMMIT; exit 3; }
test "$(git rev-parse 'HEAD^{tree}')" = "$TREE"  || { echo E_LX_A1_TREE;   exit 3; }
echo "A1 ok"
# DEV-LX-1: a sparse index also lists skip-worktree entries (tag S); A2 binds only the checked-out ones (tag H)
git ls-files -s -t | awk '$1=="H"' | cut -c3- > ../meta/ls-files.txt
git sparse-checkout list > ../meta/SPARSE.applied
git fsck --no-dangling > ../meta/fsck.txt 2>&1 || echo "fsck rc!=0 archived; A2 is binding" >> ../meta/fsck.txt
python3 -I "$ROOT/tools/lx_meta.py" provenance "$D" "$SHA" "$TREE" > ../meta/PROVENANCE.json
rm -rf .git
find . -type f -print0 | sort -z | xargs -0 sha256sum > ../meta/SHA256SUMS
python3 -I "$ROOT/tools/lx_meta.py" manifest "$D" > ../meta/MANIFEST.jsonl
set +e; python3 -I "$ROOT/tools/lx_meta.py" gates "$D" > ../meta/GATES.json; rc=$?; set -e
cat ../meta/GATES.json | head -40
[ $rc -eq 0 ] || { echo "E_LX_GATES rc=$rc"; exit $rc; }
chmod -R a-w "$D/src"
[ -n "${LX_PIN_DIR:-}" ] || { ln -sfn "$D" "$ROOT/CURRENT.new" && mv -T "$ROOT/CURRENT.new" "$ROOT/CURRENT"; }
echo "LX_ACQUIRE_OK"
