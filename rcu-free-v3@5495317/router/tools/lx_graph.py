#!/usr/bin/env python3
"""lx_graph.py - BT-LXR-08: merge the stage graphs (includes, kconfig, calls) into one typed graph.json per book,
add PHASE tags and the HB2-11 sub-anchors of router symbols larger than 1,800 B.

usage: lx_graph.py [--check]     writes X/hb/<book>/book/graph.json (x13) and X/graph/merge.report.json
Ownership: an edge belongs to the book of its source (file or sid); KCONFIG edges to the book of their Kconfig file;
ARCH_PAIR to both sides' books. PHASE edges are per SYMBOL-layer file -> HB-KPAPER-001 anchor hb-s5.p14 (phase order
section) carrying the F-tag of spec/PHASEMAP.tsv. HOT = global CALLS fan-in > F_max = 64.
Sub-anchors: greedy line chunks <= 1,800 B covering the parent span contiguously; child sid = parent + "#b<k>".
"""
import collections, json, os, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lxlib as L  # noqa: E402
import lx_calls as C  # noqa: E402
import lx_symbols as S  # noqa: E402

SUB_MAX = 1800
F_MAX = 64
PHASE_TARGET = "HB-KPAPER-001/hb-s5.p14"


def chunks(b, start, end):
    """Contiguous [s, e) pieces of b[start:end], each <= SUB_MAX bytes, cut at line ends when possible."""
    out, s, cur = [], start, start
    while cur < end:
        nl = b.find(b"\n", cur, end)
        le = end if nl < 0 else nl + 1
        if le - s > SUB_MAX:
            if cur > s:
                out.append((s, cur))
                s = cur
            while le - s > SUB_MAX:
                out.append((s, s + SUB_MAX))
                s += SUB_MAX
        cur = le
    if s < end:
        out.append((s, end))
    return out


def check_subanchors(parents, children, src=None):
    """g_subanchor: children of each parent concatenate exactly to its body, each <= 1,800 B. -> (ok, detail)."""
    kids = collections.defaultdict(list)
    for p, c, s, e in children:
        kids[p].append((s, e, c))
    bad_size = sum(1 for _, _, s, e in children if e - s > SUB_MAX)
    bad_cover = 0
    for p in parents:
        ks = sorted(kids.get(p["sid"], []))
        pos = p["start"]
        for s, e, _ in ks:
            if s != pos:
                bad_cover += 1
                break
            pos = e
        if pos != p["end"]:
            bad_cover += 1
        if src is not None and ks:
            b = src(p["path"])
            if L.sha256b(b"".join(b[s:e] for s, e, _ in ks)) != L.sha256b(b[p["start"]:p["end"]]):
                bad_cover += 1
    return bad_size == 0 and bad_cover == 0 and len(parents) > 0, f"parents={len(parents)} children={len(children)} over_1800={bad_size} cover_errors={bad_cover}"


def build():
    syms = C.load_symbols()
    sym_book = {s["sid"]: s["book"] for s in syms}
    inc = L.jload(os.path.join(L.X, "graph", "includes.json"))
    kc = L.jload(os.path.join(L.X, "graph", "kconfig.json"))
    ca = L.jload(os.path.join(L.X, "graph", "calls.json"))
    layer = set(S.symbol_files())
    g = {bk: collections.defaultdict(list) for bk in L.BOOK_IDS}
    st = collections.Counter()
    for f, i, t, arch, how in inc["edges"]:
        if f in layer:
            g[L.book(f)]["INCLUDES"].append([f, t, i, arch] if t else [f, None, i, arch, "ABSENT:" + how])
        else:
            st["includes_file_layer_only"] += 1
    for f, c, mk in kc["built_by"]:
        if f in layer:
            g[L.book(f)]["BUILT_BY"].append([f, c, mk])
        else:
            st["built_by_file_layer_only"] += 1
    for typ, rows in (("DEPENDS", kc["depends"]), ("SELECTS", kc["selects"])):
        for a, b, kf in rows:
            bk = L.book(kf)
            if bk:
                g[bk]["KCONFIG"].append([a, b, typ, kf])
            else:
                st["kconfig_edges_unowned"] += 1
    fanin = collections.Counter()
    for a, b, amb in ca["calls"]:
        g[sym_book[a]]["CALLS"].append([a, b, amb])
        fanin[b] += 1
    for a, b, fld, stc, amb in ca["ops"]:
        g[sym_book[a]]["OPS"].append([a, b, fld, stc, amb])
    for q, a, b, amb in ca["arch_pair"]:
        for bk in sorted({sym_book[a], sym_book[b]}):
            g[bk]["ARCH_PAIR"].append([q, a, b, amb])
    for f in sorted(layer):
        for ph in L.phases(f):
            g[L.book(f)]["PHASE"].append([f, PHASE_TARGET, ph])
    unres = ca["unresolved"]["calls_per_symbol"]
    cache = {}

    def src(p):
        if p not in cache:
            cache.clear()
            cache[p] = L.src_bytes(p)
        return cache[p]

    subs = {bk: [] for bk in L.BOOK_IDS}
    for s in sorted(syms, key=lambda s: (s["path"], s["start"], s["sid"])):
        if not s["router"] or s["end"] - s["start"] <= SUB_MAX:
            continue
        pcs = chunks(src(s["path"]), s["start"], s["end"])
        if len(pcs) > 999:
            raise L.LxError("E_SUBANCHOR_OVERFLOW", s["sid"])
        for k, (a, b) in enumerate(pcs, 1):
            subs[s["book"]].append([s["sid"], f"{s['sid']}#b{k}", a, b])
    out = {}
    tot = collections.Counter()
    for bk in L.BOOK_IDS:
        edges = {k: sorted(v, key=lambda e: json.dumps(e)) for k, v in sorted(g[bk].items())}
        hot = sorted([sid, n] for sid, n in fanin.items() if n > F_MAX and sym_book[sid] == bk)
        doc = {"schema": "lx.graph.v1", "book": bk, "evidence": "DERIVED lexical", "pin": L.PIN, "depends_on": [] if bk == "lx-inc" else ["lx-inc"],
               "columns": {"INCLUDES": ["from", "to", "inc", "arch", "absent?"], "BUILT_BY": ["file", "config", "makefile"],
                           "KCONFIG": ["from", "to", "type", "kconfig"], "CALLS": ["from", "to", "ambig"],
                           "OPS": ["from", "to", "field", "struct", "ambig"], "ARCH_PAIR": ["qualname", "arm64", "x86", "ambig"],
                           "PHASE": ["file", "anchor", "phase"], "subanchors": ["parent", "child", "start_byte", "end_byte"]},
               "edges": edges, "counts": {k: len(v) for k, v in edges.items()},
               "unresolved": {sid: n for sid, n in sorted(unres.items()) if sym_book[sid] == bk},
               "hot": {"f_max": F_MAX, "rows": hot}, "subanchors": subs[bk]}
        out[f"hb/{bk}/book/graph.json"] = L.canon(doc)
        for k, v in edges.items():
            tot[k] += len(v)
        tot["hot"] += len(hot)
        tot["subanchor_children"] += len(subs[bk])
        tot["subanchor_parents"] += len({c[0] for c in subs[bk]})
        tot["unresolved_symbols"] += len(doc["unresolved"])
    rep = {"schema": "lx.merge.report.v1", "edges_per_type": {k: tot[k] for k in ("INCLUDES", "BUILT_BY", "KCONFIG", "CALLS", "OPS", "ARCH_PAIR", "PHASE")},
           "absent_includes_in_books": sum(1 for bk in L.BOOK_IDS for e in g[bk]["INCLUDES"] if e[1] is None),
           "hot_symbols": tot["hot"], "subanchor_parents": tot["subanchor_parents"], "subanchor_children": tot["subanchor_children"],
           "symbols_with_unresolved_calls": tot["unresolved_symbols"], "not_in_books": dict(sorted(st.items()))}
    out["graph/merge.report.json"] = L.canon(rep)
    return out


def main():
    files = build()
    if "--check" in sys.argv:
        bad = [k for k, v in sorted(files.items()) if not os.path.exists(os.path.join(L.X, k)) or open(os.path.join(L.X, k), "rb").read() != v]
        print(json.dumps({"check": "byte-identical" if not bad else "DIFFERENT", "bad": bad}))
        return 1 if bad else 0
    for k, v in sorted(files.items()):
        L.write_bytes(os.path.join(L.X, k), v)
    print(files["graph/merge.report.json"].decode().strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
