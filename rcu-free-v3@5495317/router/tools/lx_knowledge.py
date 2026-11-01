#!/usr/bin/env python3
"""lx_knowledge.py - knowledge layer of the lx router: index the APPROVED study outputs (LinuxDistill/study/pass1) as router
nodes linked to the code symbols they cite. Deterministic: no model in the loop; same inputs => byte-identical outputs.

Levels: extract (map lanes), partial (reduce levels), dossier (finals v2). Each finding becomes one node
  {id, level, doc, dossier, kind, text, sids, resolved, review}  (review = Argon round-2 verdict when sampled, else "unreviewed")
Edges: CITES finding->sid (only sids that resolve in the router; unresolved ones are listed, never dropped silently),
       DERIVES doc->doc (dossier/partial -> the extract digests it merges).
Index: router/index/lx-knowledge/ (same lx.index.v1 format, integer BM25F) with fields text, kind, sid, dossier.
ID = sha256(study SHA256SUMS + g_lx_fresh) so a changed study file or a changed snapshot both change it.

usage: lx_knowledge.py build | query "<text>" [--k N] [--level extract|partial|dossier] | check
"""
import glob, hashlib, json, os, re, sys

sys.dont_write_bytecode = True
TOOLS = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, TOOLS)
import lxlib as L  # noqa: E402
import lx_index as IX  # noqa: E402
import lx_query as Q  # noqa: E402

STUDY = os.path.normpath(os.path.join(L.X, "..", "..", "study", "pass1"))
OUT = os.path.join(L.X, "knowledge"); IDX = os.path.join(L.X, "index", "lx-knowledge")
CATS = {"exports": "export", "invariants": "invariant", "locks": "lock", "structs": "struct", "state_machines": "state_machine",
        "entry_points": "entry_point", "hazards": "hazard"}
FIELDS = ["text", "kind", "sid", "dossier"]; WEIGHTS = {"text": 1000, "kind": 300, "sid": 1500, "dossier": 300}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def router_sids():
    s = {}
    for f in sorted(glob.glob(os.path.join(L.X, "hb", "*", "book", "anchors.jsonl"))):
        for line in open(f, encoding="utf-8"):
            r = json.loads(line); s[r["id"]] = (r["path"], r["start_byte"], r["end_byte"])
    return s


def review_flags():
    """Argon round-2 verdicts keyed by (dossier, kind, index) as sampled by argon_review2 (deterministic sample)."""
    flags = {}
    for f in sorted(glob.glob(os.path.join(STUDY, "review", "B-D??-?.json"))):
        d = os.path.basename(f)[2:5]
        try:
            o = json.load(open(f))
        except Exception:
            continue
        for v in o.get("verdicts", []):
            flags[(d, v.get("n"))] = v.get("verdict")
    return flags


def sample_map(d, o):
    """Rebuild argon_review2's deterministic sample (same seed rule) so verdict n maps back to (kind, index)."""
    import random
    cats = ["exports", "invariants", "locks", "structs", "state_machines", "entry_points", "hazards"]
    pool = [(c, i) for c in cats for i, _ in enumerate(o.get(c, []))]
    rnd = random.Random(int(hashlib.sha256(d.encode()).hexdigest()[:8], 16))
    pick = sorted(rnd.sample([(c, i, None) for c, i in pool], min(8, len(pool))), key=lambda t: (cats.index(t[0]), t[1]))
    return {n: (c, i) for n, (c, i, _) in enumerate(pick, 1)}


def docs_of():
    """-> [(level, doc_id, dossier, obj, raw_sha)] in a fixed order."""
    out = []
    for level, sub in (("extract", "extracts"), ("partial", "partials"), ("dossier", "dossiers")):
        for f in sorted(glob.glob(os.path.join(STUDY, sub, "*.json"))):
            raw = open(f, "rb").read(); o = json.loads(raw)
            out.append((level, os.path.basename(f)[:-5], o.get("dossier", ""), o, sha(raw)))
    return out


def findings(level, o):
    if level == "extract":
        for i, x in enumerate(o.get("findings", [])):
            yield x.get("kind", ""), i, x
    else:
        for c, k in CATS.items():
            for i, x in enumerate(o.get(c, [])):
                yield k, i, x


def build():
    A = router_sids(); flags = review_flags()
    nodes, cites, derives, unresolved = [], [], [], []
    for level, doc, d, o, rs in docs_of():
        smap = {}
        if level == "dossier":
            inv = {v: n for n, v in sample_map(d, o).items()}
            smap = {k: flags.get((d, n), "unreviewed") for k, n in inv.items()}
        for kind, i, x in findings(level, o):
            sids = list(x.get("sids", []))
            nid = "kn:" + sha(f"{level}|{doc}|{kind}|{i}".encode())[:20]
            ok = [s for s in sids if s in A]; bad = [s for s in sids if s not in A]
            cat = {v: c for c, v in CATS.items()}.get(kind, kind)
            nodes.append({"id": nid, "level": level, "doc": doc, "dossier": d, "kind": kind, "i": i, "text": x.get("text", ""),
                          "sids": sids, "resolved": not bad, "review": smap.get((cat, i), "unreviewed") if level == "dossier" else "unreviewed"})
            cites += [[nid, s] for s in ok]; unresolved += [[nid, s] for s in bad]
        if level != "extract":
            derives += [[doc, e] for e in o.get("extracts", [])]
    study_sums = open(os.path.join(STUDY, "SHA256SUMS"), "rb").read()
    ixid = sha(study_sums + L.fresh_id().encode())
    docs, meta = [], []
    for n in nodes:
        docs.append({"text": IX.words(n["text"]), "kind": [n["kind"]], "sid": sorted({t for s in n["sids"] for t in IX.words(s.split("::", 1)[-1])} |
                     {s.lower() for s in n["sids"]}), "dossier": [n["dossier"].lower(), n["level"]]})
        meta.append([n["id"], n["level"], n["doc"], n["dossier"], n["kind"], n["review"]])
    files = IX.serialize(docs, FIELDS, WEIGHTS, meta, ixid)
    os.makedirs(IDX, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    for k, v in files.items():
        L.write_bytes(os.path.join(IDX, k), v)
    L.write_jsonl(os.path.join(OUT, "nodes.jsonl"), nodes)
    L.write_jsonl(os.path.join(OUT, "cites.jsonl"), [{"src": a, "dst": b} for a, b in cites])
    L.write_jsonl(os.path.join(OUT, "derives.jsonl"), [{"src": a, "dst": b} for a, b in derives])
    L.write_jsonl(os.path.join(OUT, "unresolved.jsonl"), [{"src": a, "sid": b} for a, b in unresolved])
    stats = {"schema": "lx.knowledge.v1", "index_id": ixid, "nodes": len(nodes),
             "by_level": {lv: sum(n["level"] == lv for n in nodes) for lv in ("extract", "partial", "dossier")},
             "cites": len(cites), "unresolved": len(unresolved), "derives": len(derives),
             "reviewed": {v: sum(n["review"] == v for n in nodes) for v in sorted({n["review"] for n in nodes})}}
    L.write_json(os.path.join(OUT, "stats.json"), stats)
    print(json.dumps(stats))


def query(text, k=8, level=None):
    ix = Q.Index(IDX, None); A = router_sids()
    nodes = {n["id"]: n for n in L.read_jsonl(os.path.join(OUT, "nodes.jsonl"))}
    S = ix.scores(IX.words(text) + [t.lower() for t in text.split()])
    order = sorted(S, key=lambda dd: (-S[dd], dd))
    res = []
    for dd in order:
        m = ix.docs[dd]; n = nodes[m[0]]
        if level and n["level"] != level:
            continue
        locs = [f"{A[s][0]}@{A[s][1]}-{A[s][2]}" for s in n["sids"][:3] if s in A]
        res.append({"score": S[dd], "level": n["level"], "dossier": n["dossier"], "kind": n["kind"], "review": n["review"],
                    "text": n["text"][:240], "sids": n["sids"][:4], "code": locs})
        if len(res) == k:
            break
    print(json.dumps(res, indent=1, ensure_ascii=False))


def check():
    """Gate: index integrity + every CITES edge resolves + unresolved listed + rebuild byte-identical (compare to current)."""
    before = {p: open(p, "rb").read() for p in sorted(glob.glob(os.path.join(IDX, "*")) + glob.glob(os.path.join(OUT, "*")))}
    build()
    after = {p: open(p, "rb").read() for p in before}
    same = all(before[p] == after[p] for p in before)
    A = router_sids()
    bad = [c for c in L.read_jsonl(os.path.join(OUT, "cites.jsonl")) if c["dst"] not in A]
    Q.Index(IDX, None)                               # raises E_CHUNK_SHA on any tampered index file
    ok = same and not bad
    print(json.dumps({"gate": "G-LX-KNOW", "rebuild_identical": same, "cites_unresolved_in_edges": len(bad), "pass": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["build"]:
        build()
    elif a[:1] == ["query"] and len(a) >= 2:
        k = int(a[a.index("--k") + 1]) if "--k" in a else 8
        lv = a[a.index("--level") + 1] if "--level" in a else None
        query(a[1], k, lv)
    elif a[:1] == ["check"]:
        sys.exit(check())
    else:
        print(__doc__); sys.exit(2)
