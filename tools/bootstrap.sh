#!/usr/bin/env bash
# tools/bootstrap.sh - fetch the pinned Linux snapshot, rebuild the router and the knowledge layer, run every gate.
# Safe to re-run: a snapshot already in place is kept. Needs git >= 2.25, python3, Universal Ctags, zstd, network to github.com.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
D="$ROOT/rcu-free-v3@5495317"; A="$ROOT/.acquire"
if [ ! -d "$D/src" ]; then
  [ ! -e "$A" ] || { chmod -R u+w "$A"; rm -rf "$A"; }
  mkdir -p "$A"
  LX_PIN_DIR="$A/rcu-free-v3@5495317" bash "$ROOT/tools/lx_acquire.sh"
  cmp "$A/rcu-free-v3@5495317/meta/SHA256SUMS" "$D/meta/SHA256SUMS" || { echo "E_SNAPSHOT_DIFFERS"; exit 4; }
  chmod u+w "$A/rcu-free-v3@5495317/src"
  mv "$A/rcu-free-v3@5495317/src" "$D/src"
  chmod a-w "$D/src"
  chmod -R u+w "$A"; rm -rf "$A"
  echo "SNAPSHOT_IDENTICAL"
fi
( cd "$ROOT/study/pass1" && sha256sum -c SHA256SUMS --quiet )
bash "$D/router/build.sh"
bash "$D/router/gates/run_all.sh"
python3 -I -B "$D/router/tools/lx_knowledge.py" build
python3 -I -B "$D/router/tools/lx_knowledge.py" check
echo "BOOTSTRAP_OK"
