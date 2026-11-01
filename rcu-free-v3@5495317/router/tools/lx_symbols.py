#!/usr/bin/env python3
"""lx_symbols.py - BT-LXR-03: ctags JSON -> hb.symbol.v2 / hb.anchor.v2 per book, sid rules LX-SID-a..d, node ids (H rule A1).

usage: lx_symbols.py [--check]
SYMBOL layer = T0-S code files (.c .h .S) + the kept ROUTE closure of BT-LXR-05 (closure/route_closure.txt).
Producer: /usr/bin/ctags with tools/lx_macros.ctags for C; LX-SID-d lexical labels for .S.
Router nodes: function, struct, union, enum, typedef, variable, function-like macro, asm label. Object-like macros
and unexpanded TRACE_EVENT / DECLARE_* / DEFINE_* invocations are lookup rows only (in symbols.jsonl, no node id).
Members and enumerators stay inside the parent span. Profile lx-gnuc kind projection onto the closed hb.symbol.v2
enum: function|macro|asm -> function, struct|union|enum|typedef -> class, variable|object-macro|lookup -> constant;
the native C kind is kept in idmap.jsonl. Clean room: sig is "<ckind> <qualname>" (the C signature is only hashed).
Writes X/hb/<book>/book/{symbols,anchors,idmap,nodemap}.jsonl and X/hb/lx_symbols.report.json.
"""
import collections, json, os, re, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lxlib as L  # noqa: E402

ROUTER_C = {"function", "struct", "union", "enum", "typedef", "variable"}
LOOKUP_NAME = re.compile(r"^(TRACE_EVENT\w*|DECLARE_\w+|DEFINE_\w+)$")
HB_KIND = {"function": "function", "macro_fn": "function", "asm_label": "function", "struct": "class", "union": "class",
           "enum": "class", "typedef": "class", "variable": "constant", "macro_obj": "constant", "lookup": "constant"}
GOVERNS = {"sections": [], "inv": [], "au": [], "none_declared": True}


def symbol_files():
    man = L.manifest()
    t0s = {p for p, r in man.items() if r["tier"] == "T0-S" and L.is_code(p)}
    with open(os.path.join(L.X, "closure", "route_closure.txt")) as f:
        clo = {l.strip() for l in f if l.strip()}
    return sorted(t0s | clo)


def assign(recs):
    """recs: dicts with path, qual, start_byte. Sets rec['sid'] by LX-SID-a/c; raises E_SID_COLLISION on a duplicate
    sid without .alt_k (e.g. two raw paths that escape to one string) and E_SID_PATTERN / E_SID_ANON on bad sids."""
    groups = collections.defaultdict(list)
    for r in recs:
        groups[(r["path"], r["qual"])].append(r)
    for (path, qual), rs in groups.items():
        rs.sort(key=lambda r: (r["start_byte"], r.get("_i", 0)))
        if len(rs) == 1:
            rs[0]["sid"] = f"{L.esc_path(path)}::{qual}"
            rs[0]["alt"] = 0
        else:
            for k, r in enumerate(rs, 1):
                r["sid"] = f"{L.esc_path(path)}::{qual}.alt_{k}"
                r["alt"] = k
    seen = {}
    for r in recs:
        s = r["sid"]
        if "__anon" in s:
            raise L.LxError("E_SID_ANON", s)
        if len(s) > 200 or not L.SID_RE.fullmatch(s):
            raise L.LxError("E_SID_PATTERN", s)
        if s in seen:
            raise L.LxError("E_SID_COLLISION", f"{s} <- {seen[s]} and {r['path']}")
        seen[s] = r["path"]
    return recs


def node_ids(sids):
    """H = 12 corpus-wide, 16 on any collision, collision at 16 = E_NODE_ID_COLLISION (amendment A1)."""
    for H in (12, 16):
        m = {s: L.node_id(s, H) for s in sids}
        if len(set(m.values())) == len(m):
            return H, m
    raise L.LxError("E_NODE_ID_COLLISION", "H=16")


def qualify(tags):
    """ctags tags of ONE file (emission order) -> records with qual (LX-SID-b anon_k) for the kept kinds."""
    raw2q, anon_n, out = {}, collections.Counter(), []

    def scope_q(scope):
        if not scope:
            return ""
        if scope in raw2q:
            return raw2q[scope]
        return scope.replace("::", ".")      # unseen parent: an __anon piece here is caught as E_SID_ANON

    for t in tags:
        name, scope, kind = t["name"], t.get("scope", ""), t["kind"]
        full = f"{scope}::{name}" if scope else name
        parent = scope_q(scope)
        if name.startswith("__anon"):
            anon_n[parent] += 1
            q = (parent + "." if parent else "") + f"anon_{anon_n[parent]}"
        else:
            q = (parent + "." if parent else "") + name
        raw2q[full] = q
        if kind in ("member", "enumerator"):
            continue
        if t.get("scopeKind") == "function":
            continue
        if kind == "macro":
            ck = "macro_fn" if "signature" in t else "macro_obj"
        elif kind == "function" and LOOKUP_NAME.match(name):
            ck = "lookup"
        elif kind in ROUTER_C:
            ck = kind
        else:
            continue
        out.append({"path": t["path"], "qual": q, "name": name if not name.startswith("__anon") else q.rsplit(".", 1)[-1],
                    "ckind": ck, "l1": t["line"], "l2": max(t["line"], t.get("end", t["line"])),
                    "sigtxt": t.get("signature"), "_i": t["_i"]})
    return out


def doc_span(b, start):
    """Byte span of the block comment that ends right before `start` (whitespace between), or None."""
    j = start
    while j > 0 and b[j - 1:j] in (b" ", b"\t", b"\n", b"\r"):
        j -= 1
    if j >= 2 and b[j - 2:j] == b"*/":
        i = b.rfind(b"/*", 0, j - 2)
        if i >= 0:
            return i, j
    return None


def build():
    files = symbol_files()
    man = L.manifest()
    recs = []
    ctags = L.run_ctags([p for p in files if L.ext_of(p) in ("c", "h")])
    by_path = collections.defaultdict(list)
    for t in ctags:
        by_path[t["path"]].append(t)
    for p in files:
        if L.ext_of(p) == "S":
            for i, (n, l1, l2) in enumerate(L.asm_labels(L.src_bytes(p))):
                recs.append({"path": p, "qual": n, "name": n, "ckind": "asm_label", "l1": l1, "l2": l2, "sigtxt": None, "_i": i})
        else:
            recs += qualify(by_path.get(p, []))
    content = {}
    for r in recs:
        p = r["path"]
        if p not in content:
            b = L.src_bytes(p)
            content[p] = (b, L.line_starts(b))
        b, st = content[p]
        r["start_byte"], r["end_byte"] = L.span_of_lines(st, len(b), r["l1"], r["l2"])
    assign(recs)
    router = [r for r in recs if r["ckind"] not in ("macro_obj", "lookup")]
    H, nid = node_ids(sorted(r["sid"] for r in router))
    per = collections.defaultdict(lambda: {"symbols": [], "anchors": [], "idmap": [], "nodemap": []})
    stats = collections.Counter()
    for r in sorted(recs, key=lambda r: r["sid"].encode()):
        p = r["path"]
        bk = L.book(p)
        if bk is None:
            raise L.LxError("E_NO_BOOK", p)
        b, st = content[p]
        span = b[r["start_byte"]:r["end_byte"]]
        sha = L.sha256b(span)
        ast = L.lex_sha(span)
        sym = {"schema": "hb.symbol.v2", "id": r["sid"], "kind": HB_KIND[r["ckind"]], "path": p,
               "span": {"start_byte": r["start_byte"], "end_byte": r["end_byte"], "start_line": r["l1"], "end_line": r["l2"]},
               "sha256": sha, "sha256_ast": ast, "sig": f"{r['ckind']} {r['qual']}"[:160], "governs": GOVERNS,
               "bytes": r["end_byte"] - r["start_byte"]}
        if r["sigtxt"] is not None:
            sym["signature_sha256"] = L.sha256b(r["sigtxt"].encode())
        ds = doc_span(b, r["start_byte"])
        anc = {"schema": "hb.anchor.v2", "id": r["sid"], "path": p, "symbol": r["sid"], "role": "symbol", "kind": sym["kind"],
               "span": {"start_line": r["l1"], "end_line": r["l2"]}, "sha256": sha, "lang": "other",
               "start_byte": r["start_byte"], "end_byte": r["end_byte"], "sha256_ast": ast,
               "doc_sha256": L.sha256b(b[ds[0]:ds[1]]) if ds else L.L.EMPTY_SHA256, "status": "active", "redirect_to": None}
        is_router = r["ckind"] not in ("macro_obj", "lookup")
        d = per[bk]
        d["symbols"].append(sym)
        d["anchors"].append(anc)
        d["idmap"].append({"sid": r["sid"], "path": p, "ckind": r["ckind"], "name": r["name"], "qual": r["qual"], "alt": r["alt"],
                           "router": is_router, "line": r["l1"], "tier": man[p]["tier"]})
        if is_router:
            d["nodemap"].append({"node": nid[r["sid"]], "sid": r["sid"]})
        stats[bk] += 1
        stats["ck:" + r["ckind"]] += 1
        stats["router" if is_router else "lookup"] += 1
    out = {}
    for bk in L.BOOK_IDS:
        d = per[bk]
        for k in ("symbols", "anchors", "idmap", "nodemap"):
            out[f"hb/{bk}/book/{k}.jsonl"] = L.jsonl_bytes(d[k])
    rep = {"schema": "lx.symbols.report.v1", "symbol_layer_files": len(files), "records": len(recs), "H": H,
           "router_nodes": stats["router"], "lookup_rows": stats["lookup"],
           "per_book": {bk: stats[bk] for bk in L.BOOK_IDS},
           "per_book_router": {bk: len(per[bk]["nodemap"]) for bk in L.BOOK_IDS},
           "by_ckind": {k[3:]: v for k, v in sorted(stats.items()) if k.startswith("ck:")},
           "alt_groups": len({(r["path"], r["qual"]) for r in recs if r["alt"]}),
           "alt_members": sum(1 for r in recs if r["alt"]),
           "c_files": sum(1 for p in files if L.ext_of(p) == "c"), "c_symbols": sum(1 for r in recs if r["path"].endswith(".c"))}
    out["hb/lx_symbols.report.json"] = L.canon(rep)
    return out


def main():
    files = build()
    if "--check" in sys.argv:
        bad = [k for k, v in sorted(files.items()) if not os.path.exists(os.path.join(L.X, k)) or open(os.path.join(L.X, k), "rb").read() != v]
        print(json.dumps({"check": "byte-identical" if not bad else "DIFFERENT", "bad": bad[:5]}))
        return 1 if bad else 0
    for k, v in sorted(files.items()):
        L.write_bytes(os.path.join(L.X, k), v)
    print(files["hb/lx_symbols.report.json"].decode().strip())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except L.LxError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
