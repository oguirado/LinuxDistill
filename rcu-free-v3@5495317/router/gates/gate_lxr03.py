#!/usr/bin/env python3
"""BT-LXR-03 gate: every sid full-matches the hb.defs.v2 sid pattern (no ctags __anon id), every record validates
hb.symbol.v2 / hb.anchor.v2, sid<->node maps are bijective, and lx_symbols.py --check is byte-identical.
must-FAIL: two synthetic natives that project to one sid without .alt_k (escaped paths) => E_SID_COLLISION."""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gatelib import X, main
import lxlib as L
import lx_symbols as S


def positive():
    bad_sid = invalid = 0
    nodes, sids, router = [], [], set()
    n_sym = 0
    for bk in L.BOOK_IDS:
        d = L.book_dir(bk)
        syms = L.read_jsonl(os.path.join(d, "symbols.jsonl"))
        ancs = L.read_jsonl(os.path.join(d, "anchors.jsonl"))
        n_sym += len(syms)
        for s in syms:
            if not L.SID_RE.fullmatch(s["id"]) or "__anon" in s["id"]:
                bad_sid += 1
            invalid += bool(L.validate(s, "hb.symbol.v2"))
        invalid += sum(bool(L.validate(a, "hb.anchor.v2")) for a in ancs)
        router |= {r["sid"] for r in L.read_jsonl(os.path.join(d, "idmap.jsonl")) if r["router"]}
        for r in L.read_jsonl(os.path.join(d, "nodemap.jsonl")):
            nodes.append(r["node"]); sids.append(r["sid"])
    bij = len(set(nodes)) == len(nodes) == len(set(sids)) and set(sids) == router
    env = dict(L.ENV, TZ="America/Lima", PYTHONHASHSEED="777")
    p = subprocess.run([sys.executable, "-I", "-B", os.path.join(X, "tools", "lx_symbols.py"), "--check"], cwd="/", env=env, capture_output=True, text=True)
    ok = n_sym > 0 and bad_sid == 0 and invalid == 0 and bij and p.returncode == 0
    return ok, f"records={n_sym} bad_sid={bad_sid} schema_invalid={invalid} nodes={len(nodes)} bijective={bij} check={p.stdout.strip()[:60]}"


def must_fail():
    recs = L.read_jsonl(os.path.join(X, "fixtures", "lx", "symbols", "collision.jsonl"))
    try:
        S.assign(recs)
    except L.LxError as e:
        return False, str(e)[:160]
    return True, "no collision detected"


if __name__ == "__main__":
    main(positive, must_fail)
