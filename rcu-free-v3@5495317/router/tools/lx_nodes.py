#!/usr/bin/env python3
"""lx_nodes.py - BT-LXR-02: the lx FILE layer (one ctx.node.v2 per KEEP_LX file of the fetch pool).

usage: lx_nodes.py [--check]
Reads the path list from meta/MANIFEST.jsonl (no git), derives ids and compiles nodes through the UNCHANGED
MetaViewer compiler entry points (_derive_ids, compile_material) with the kit ctx.node.v2 schema and validator,
then sets the lx fields of section 5.1 rule 5. Clean room: title = path and purpose = a synthetic line (the
first block comment is GPL text, so only its byte span is kept in nodes/lx.title_spans.jsonl).
Writes X/nodes/lx.jsonl, X/routes/lx.tsv, X/nodes/lx.title_spans.jsonl, X/nodes/lx.report.json.
--check rebuilds in memory and exits 1 unless every file is byte-identical.
"""
import collections, importlib.util, json, os, re, sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lxlib as L  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


KCONF = re.compile(r"^\s*(?:menu)?config\s+([A-Za-z0-9_]+)", re.M)
SPDX = re.compile(rb"SPDX-License-Identifier")


def title_span(b):
    """Byte span of the first block comment after the SPDX line (pointer only, never copied)."""
    head = b[:8192]
    m = SPDX.search(head)
    start = head.find(b"\n", m.end()) + 1 if m else 0
    i = head.find(b"/*", start)
    if i < 0:
        return None
    j = head.find(b"*/", i + 2)
    return None if j < 0 else [i, j + 2]


def anchors_for(paths):
    """Top-level definitions (byte order, <= 16) per path: ctags with lx_macros for .c/.h, LX-SID-d labels for .S,
    `config` names for Kconfig files."""
    out = collections.defaultdict(list)
    ch = [p for p in paths if L.ext_of(p) in ("c", "h")]
    for t in L.run_ctags(ch):
        if "scope" in t or t["name"].startswith("__anon"):
            continue
        k = t["kind"]
        if k in ("function", "struct", "union", "enum", "typedef", "variable") or (k == "macro" and "signature" in t):
            out[t["path"]].append((t["line"], t["name"]))
    for p in paths:
        b = p.rsplit("/", 1)[-1]
        if L.ext_of(p) == "S":
            out[p] = [(l1, n) for n, l1, _ in L.asm_labels(L.src_bytes(p))]
        elif b.startswith("Kconfig"):
            t = L.src_bytes(p).decode("latin-1")
            out[p] = [(t.count("\n", 0, m.start()) + 1, m.group(1)) for m in KCONF.finditer(t)]
    res = {}
    for p, v in out.items():
        seen, names = set(), []
        for _, n in sorted(v):
            if n not in seen and len(n) <= 64:
                seen.add(n)
                names.append(n)
        res[p] = names[:16]
    return res


def build():
    man = L.manifest()
    paths = sorted((p for p in man if L.keep_lx(p)), key=lambda s: s.encode())
    mv = load("mv_router_index", os.path.join(L.MV_ROUTER, "ref", "router_index.metaviewer.py"))
    validate = load("kit_jsonschema_lite", os.path.join(L.MV_ROUTER, "kit", "tools", "jsonschema_lite.py")).validate
    schema = L.jload(os.path.join(L.MV_ROUTER, "kit", "standards", "schemas", "ctx.node.v2.schema.json"))
    ids = mv._derive_ids(paths, L.CORPUS)
    mat = mv.compile_material(Path(L.SRC), tuple(paths), corpus=L.CORPUS, ids=ids, schema=schema, validate=validate)
    rel_by_id = {v: k for k, v in ids.items()}
    anch = anchors_for(paths)
    nodes, spans = [], []
    stats = collections.Counter()
    for line in mat.nodes_jsonl.decode("utf-8").splitlines():
        n = json.loads(line)
        p = rel_by_id[n["id"]]
        m = man[p]
        if n["source_sha256"] != m["sha256"]:
            raise L.LxError("E_MANIFEST_SHA", p)
        fam = L.book(p) if L.is_code(p) and m["tier"] in ("T0-S", "T0-I") else None
        fam = fam or "lx-files"
        n["title"] = p if len(p) <= 240 else p[-240:]
        n["purpose"] = f"lx {m['tier']} {m['lang']} file {p}; family {fam}; pinned {L.PIN[:7]}"[:600]
        names = anch.get(p) or []
        n["anchors"] = [{"a": a, "role": "symbol"} for a in names] or [{"a": "file", "role": "section"}]
        n["family"] = fam
        ph = L.phases(p)
        n["domains"] = [{"domain": x, "strength": "strong"} for x in ph][:10] + [{"domain": L.arch_tag(p), "strength": "moderate"}]
        kw = list(n["search"].get("keywords", []))
        for a in names:
            if a not in kw and len(kw) < 24:
                kw.append(a[:64])
        n["search"]["keywords"] = kw
        errs = validate(n, schema)
        if errs:
            raise L.LxError("E_SCHEMA", f"{p}: {str(errs[0])[:160]}")
        nodes.append(n)
        ts = title_span(L.src_bytes(p)) if L.ext_of(p) in ("c", "h", "S") else None
        if ts:
            spans.append({"id": n["id"], "path": p, "start_byte": ts[0], "end_byte": ts[1]})
        stats[m["tier"]] += 1
        stats["family:" + fam] += 1
    nodes_b = L.jsonl_bytes(nodes)
    rep = {"schema": "lx.nodes.report.v1", "pool_files": len(man), "file_nodes": len(nodes),
           "skipped_not_keep_lx": len(man) - len(paths), "by_tier": {k: v for k, v in sorted(stats.items()) if ":" not in k},
           "by_family": {k[7:]: v for k, v in sorted(stats.items()) if k.startswith("family:")},
           "t2r_rows": "ABSENT", "title_spans": len(spans), "ids_unique": len({n['id'] for n in nodes}) == len(nodes)}
    return {"nodes/lx.jsonl": nodes_b, "routes/lx.tsv": mat.routes_tsv,
            "nodes/lx.title_spans.jsonl": L.jsonl_bytes(spans), "nodes/lx.report.json": L.canon(rep)}


def main():
    files = build()
    if "--check" in sys.argv:
        bad = [k for k, v in sorted(files.items()) if not os.path.exists(os.path.join(L.X, k)) or open(os.path.join(L.X, k), "rb").read() != v]
        print(json.dumps({"check": "byte-identical" if not bad else "DIFFERENT", "files": sorted(files), "bad": bad}))
        return 1 if bad else 0
    for k, v in sorted(files.items()):
        L.write_bytes(os.path.join(L.X, k), v)
    print(files["nodes/lx.report.json"].decode().strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
