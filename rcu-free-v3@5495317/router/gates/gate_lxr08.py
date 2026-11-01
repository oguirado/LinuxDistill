#!/usr/bin/env python3
"""BT-LXR-08 gate (g_subanchor). Positive: in every book graph the sub-anchor children of each router symbol larger
than 1,800 B concatenate exactly to the parent body (contiguous spans and sha256 of the concatenated src bytes),
each child <= 1,800 B; all 13 graphs carry the 7 edge types in total; --check byte-identical.
must-FAIL: a synthetic sub-anchor list with one child of 1,801 B."""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gatelib import X, main
import lxlib as L
import lx_calls as C
import lx_graph as G


def positive():
    syms = {s["sid"]: s for s in C.load_symbols()}
    parents, children, types = [], [], set()
    for bk in L.BOOK_IDS:
        g = L.jload(os.path.join(L.book_dir(bk), "graph.json"))
        types |= set(g["edges"])
        children += g["subanchors"]
        for sid in sorted({c[0] for c in g["subanchors"]}):
            s = syms[sid]
            parents.append({"sid": sid, "path": s["path"], "start": s["start"], "end": s["end"]})
    big = sum(1 for s in syms.values() if s["router"] and s["end"] - s["start"] > G.SUB_MAX)
    ok, det = G.check_subanchors(parents, children, src=L.src_bytes)
    p = subprocess.run([sys.executable, "-I", "-B", os.path.join(X, "tools", "lx_graph.py"), "--check"], cwd="/", env=dict(L.ENV, PYTHONHASHSEED="9"), capture_output=True, text=True)
    need = {"INCLUDES", "BUILT_BY", "KCONFIG", "CALLS", "OPS", "ARCH_PAIR", "PHASE"}
    return ok and big == len(parents) and need <= types and p.returncode == 0, f"{det} big_symbols={big} edge_types={sorted(types)} check_rc={p.returncode}"


def must_fail():
    fx = L.jload(os.path.join(X, "fixtures", "lx", "graph", "child_over_1800.json"))
    return G.check_subanchors(fx["parents"], fx["children"])


if __name__ == "__main__":
    main(positive, must_fail)
