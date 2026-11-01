#!/usr/bin/env python3
"""lx_index.py - BT-LXR-09: lexical BM25F indexes (K = 1,200,000, B = 750,000 ppm; hblib2 integer arithmetic).

usage: lx_index.py [--out DIR] [--check]
Writes X/index/lx/ (FILE layer) and X/index/lx-<book>/ x13, each {cols.json, post.json, docs.json, ID, SHA256SUMS}.
index/ID = the g_lx_fresh digest (section 5.11) of the freshness inputs, identical in every index dir; SHA256SUMS
covers the other files of the dir (content integrity, checked on mount and on shard unpack).
Symbol fields: nm (exact lower-case name and qualname, one token each), name (split identifier words), path, kind.
FILE fields: nm (exact path and basename), path (path words), kw (search keywords + anchors), fam (family, domains).
Weights are permille [TARGET-CHOSEN]; no dense index (v1).
"""
import json, os, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lxlib as L  # noqa: E402

HB = L.L
SYM_FIELDS = ["nm", "name", "path", "kind"]
SYM_W = {"nm": 3000, "name": 1500, "path": 500, "kind": 200}
FILE_FIELDS = ["nm", "path", "kw", "fam"]
FILE_W = {"nm": 3000, "path": 1500, "kw": 800, "fam": 300}


def words(s):
    return HB.toks(HB.split_ident(s))


def serialize(docs, fields, weights, meta_docs, ixid):
    ix = HB.bm25f_index(docs, fields)
    post = {}
    for t in sorted(ix["post"]):
        zs, dfs = {}, set()
        for f in fields:
            dm = ix["post"][t].get(f)
            if dm:
                zs[f] = [x for d in sorted(dm) for x in (d, dm[d])]
                dfs |= set(dm)
        post[t] = {"d": len(dfs), "i": HB.idf_ppm(ix["N"], len(dfs)), "z": zs}
    cols = {"schema": "lx.index.v1", "N": ix["N"], "fields": fields, "A": ix["A"], "len": ix["lens"], "K": HB.K_BM, "B": HB.B_PPM, "weights": weights}
    files = {"cols.json": L.canon(cols), "post.json": L.canon(post), "docs.json": L.canon(meta_docs), "ID": (ixid + "\n").encode()}
    files["SHA256SUMS"] = "".join(f"{L.sha256b(files[k])}  {k}\n" for k in sorted(files)).encode()
    return files


def book_docs(bk):
    d = L.book_dir(bk)
    spans = {s["id"]: s["span"] for s in L.read_jsonl(os.path.join(d, "symbols.jsonl"))}
    node = {r["sid"]: r["node"] for r in L.read_jsonl(os.path.join(d, "nodemap.jsonl"))}
    rows = sorted((r for r in L.read_jsonl(os.path.join(d, "idmap.jsonl")) if r["router"]), key=lambda r: r["sid"].encode())
    docs, meta = [], []
    for r in rows:
        sp = spans[r["sid"]]
        docs.append({"nm": sorted({r["name"].lower(), r["qual"].lower()}), "name": words(r["qual"]), "path": words(r["path"]), "kind": [r["ckind"]]})
        meta.append([r["sid"], node[r["sid"]], r["path"], sp["start_byte"], sp["end_byte"], r["ckind"]])
    return docs, meta


def file_docs():
    nodes = L.read_jsonl(os.path.join(L.X, "nodes", "lx.jsonl"))
    routes = {}
    with open(os.path.join(L.X, "routes", "lx.tsv")) as f:
        for i, line in enumerate(f):
            if i:
                a, b = line.rstrip("\n").split("\t")
                routes[a] = b
    docs, meta = [], []
    for n in sorted(nodes, key=lambda n: routes[n["id"]].encode()):
        p = routes[n["id"]]
        kw = list(n["search"].get("keywords", [])) + [a["a"] for a in n["anchors"]]
        docs.append({"nm": sorted({p.lower(), p.rsplit("/", 1)[-1].lower()}), "path": words(p), "kw": sorted(set(t for k in kw for t in words(k))),
                     "fam": words(n["family"]) + [d["domain"].lower() for d in n.get("domains", [])]})
        meta.append([n["id"], p, n["family"], n["source_sha256"]])
    return docs, meta


def build():
    ixid = L.fresh_id()
    out = {}
    docs, meta = file_docs()
    for k, v in serialize(docs, FILE_FIELDS, FILE_W, meta, ixid).items():
        out[f"index/lx/{k}"] = v
    for bk in L.BOOK_IDS:
        docs, meta = book_docs(bk)
        for k, v in serialize(docs, SYM_FIELDS, SYM_W, meta, ixid).items():
            out[f"index/{bk}/{k}"] = v
    return ixid, out


def main():
    a = sys.argv[1:]
    root = a[a.index("--out") + 1] if "--out" in a else L.X
    ixid, files = build()
    if "--check" in a:
        bad = [k for k, v in sorted(files.items()) if not os.path.exists(os.path.join(root, k)) or open(os.path.join(root, k), "rb").read() != v]
        print(json.dumps({"check": "byte-identical" if not bad else "DIFFERENT", "bad": bad}))
        return 1 if bad else 0
    for k, v in sorted(files.items()):
        L.write_bytes(os.path.join(root, k), v)
    print(json.dumps({"index_id": ixid, "dirs": 14, "bytes": sum(len(v) for v in files.values()),
                      "per_dir_bytes": {d: sum(len(v) for k, v in files.items() if k.split("/")[1] == d) for d in sorted({k.split("/")[1] for k in files})}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
