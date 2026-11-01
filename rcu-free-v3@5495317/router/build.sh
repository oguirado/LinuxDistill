#!/usr/bin/env bash
# build.sh - rebuild the whole lx router in Kahn order (BT-LXR-01..11) and record wall times in BUILD_TIMES.json.
# BT-LXR-01 (tools/lx_macros.ctags + fixtures) is a pinned static table: nothing to run.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1 LC_ALL=C TZ=UTC
X="$(cd "$(dirname "$0")" && pwd)"; T="$X/tools"; times=()
step() { local id="$1"; shift; local t0; t0=$(date +%s.%N); python3 -I -B "$@" > "$X/.build_$id.log"; local t1; t1=$(date +%s.%N)
         times+=("\"$id\": $(python3 -I -B -c "print(round($t1-$t0,2))")"); echo "$id ok ($(tail -c 160 "$X/.build_$id.log" | tr '\n' ' '))"; }
step BT-LXR-02 "$T/lx_nodes.py"
step BT-LXR-05 "$T/lx_includes.py"
step BT-LXR-03 "$T/lx_symbols.py"
step BT-LXR-04 "$T/lx_books.py"
step BT-LXR-06 "$T/lx_kbuild.py"
step BT-LXR-07 "$T/lx_calls.py"
step BT-LXR-08 "$T/lx_graph.py"
step BT-LXR-09 "$T/lx_index.py"
step BT-LXR-10 "$T/lx_conf.py" gen
step BT-LXR-11 "$T/lx_shard.py" pack
( IFS=,; echo "{${times[*]}}" ) > "$X/BUILD_TIMES.json"
rm -f "$X"/.build_*.log
find "$X" -name __pycache__ -prune -exec rm -rf {} +
cat "$X/BUILD_TIMES.json"
