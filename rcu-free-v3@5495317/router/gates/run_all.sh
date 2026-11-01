#!/usr/bin/env bash
# run_all.sh - run every lx router gate (BT-LXR-01..11): one JSON line per gate
# {task, positive: PASS|FAIL, must_fail: FAIL-as-expected|DEAD}; exit 0 only if every positive passes and every
# must-FAIL leg fails (rc 1). A crashing leg (rc 2) counts as FAIL for a positive and DEAD for a must-FAIL.
export PYTHONDONTWRITEBYTECODE=1 LC_ALL=C TZ=UTC
G="$(cd "$(dirname "$0")" && pwd)"; status=0; npass=0; nexp=0
for n in 01 02 03 04 05 06 07 08 09 10 11; do
  python3 -I -B "$G/gate_lxr$n.py" positive > /dev/null 2>&1; p=$?
  python3 -I -B "$G/gate_lxr$n.py" must_fail > /dev/null 2>&1; m=$?
  if [ $p -eq 0 ]; then pos=PASS; npass=$((npass+1)); else pos=FAIL; status=1; fi
  if [ $m -eq 1 ]; then mf=FAIL-as-expected; nexp=$((nexp+1)); else mf=DEAD; status=1; fi
  echo "{\"task\": \"BT-LXR-$n\", \"positive\": \"$pos\", \"must_fail\": \"$mf\"}"
done
echo "{\"summary\": {\"positive_pass\": $npass, \"must_fail_as_expected\": $nexp, \"gates\": 11}}"
find "$G/.." -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null
exit $status
