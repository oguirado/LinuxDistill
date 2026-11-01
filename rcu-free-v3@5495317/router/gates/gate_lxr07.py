#!/usr/bin/env python3
"""BT-LXR-07 gate. Positive: for file-static functions picked mechanically (one per book, sid order), the CALLS
callers equal the `grep -nw` cross-check; every CALLS/OPS/ARCH_PAIR endpoint is a SYMBOL-layer sid of the fetch pool.
must-FAIL: a synthetic calls.json with an edge to a drivers/gpu symbol (outside the fetch pool)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gatelib import X, main
import lxlib as L
import lx_calls as C
import xcheck as XC


def endpoints_ok(doc, sids):
    bad = [e for e in doc["calls"] if e[0] not in sids or e[1] not in sids]
    bad += [e for e in doc["ops"] if e[0] not in sids or e[1] not in sids]
    bad += [e for e in doc["arch_pair"] if e[1] not in sids or e[2] not in sids]
    man = L.manifest()
    bad += [e for e in doc["calls"] if e[1].split("::")[0] not in man]
    return bad


def positive():
    syms = C.load_symbols()
    sids = {s["sid"] for s in syms}
    doc = L.jload(os.path.join(X, "graph", "calls.json"))
    bad = endpoints_ok(doc, sids)
    rev = XC.callers_from_graph(doc)
    picks = XC.pick_static(syms, ["lx-sched", "lx-mm", "lx-kvm"], per_book=1)
    mism = [(s["sid"], g, sorted(rev.get(s["sid"], ()))) for s, g in picks if sorted(rev.get(s["sid"], ())) != g]
    return not bad and picks and not mism, f"endpoints_outside={len(bad)} xcheck_rows={len(picks)} mismatches={[m[0] for m in mism]} picked={[s['sid'] for s, _ in picks]}"


def must_fail():
    syms = C.load_symbols()
    doc = L.jload(os.path.join(X, "fixtures", "lx", "calls", "edge_outside_pool.json"))
    bad = endpoints_ok(doc, {s["sid"] for s in syms})
    return not bad, f"endpoints_outside={len(bad)}"


if __name__ == "__main__":
    main(positive, must_fail)
