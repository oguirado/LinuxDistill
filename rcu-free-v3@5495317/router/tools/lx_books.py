#!/usr/bin/env python3
"""lx_books.py - BT-LXR-04: longest-prefix partition of the SYMBOL layer into the 13 lx books (section 5.2),
depends_on lx-inc, one manifest per book with the node-id width H and the tool digests.

usage: lx_books.py [--check]     writes X/hb/<book>/book/manifest.json (x13)
"""
import collections, json, os, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lxlib as L  # noqa: E402
import lx_symbols as S  # noqa: E402


def partition(symbol_files, book_fn=L.book):
    """-> ({book: [files]}, unowned). Exactly one owner per file by construction of longest prefix."""
    out, unowned = collections.defaultdict(list), []
    for p in symbol_files:
        b = book_fn(p)
        (out[b].append(p) if b else unowned.append(p))
    return out, unowned


def check_partition(symbol_files, books):
    """Every SYMBOL-layer file in exactly one book: -> (ok, detail)."""
    owners = collections.Counter(p for fs in books.values() for p in fs)
    multi = sorted(p for p, n in owners.items() if n > 1)
    none = sorted(set(symbol_files) - set(owners))
    extra = sorted(set(owners) - set(symbol_files))
    return not (multi or none or extra), f"files={len(symbol_files)} books={len(books)} in_two={len(multi)} in_none={len(none)} extra={len(extra)}"


def detect_H(nodemap):
    for H in (12, 16):
        if all(r["node"].endswith("_" + L.sha256b(r["sid"].encode())[:H]) for r in nodemap):
            return H
    return None


def build():
    files = S.symbol_files()
    parts, unowned = partition(files)
    if unowned:
        raise L.LxError("E_NO_BOOK", unowned[0])
    tools = {n: L.sha_file(os.path.join(L.TOOLS, n)) for n in sorted(L.BUILDER_TOOLS + ["lx_nodes.py", "lx_macros.ctags"])
             if os.path.exists(os.path.join(L.TOOLS, n))}
    Hs = set()
    out = {}
    for bk in L.BOOK_IDS:
        d = L.book_dir(bk)
        nm = L.read_jsonl(os.path.join(d, "nodemap.jsonl"))
        H = detect_H(nm)
        Hs.add(H)
        fs = sorted(parts.get(bk, []))
        man = {"schema": "lx.book.manifest.v1", "book": bk, "corpus": L.CORPUS, "package": L.PACKAGE, "commit": L.PIN, "tree": L.TREE,
               "depends_on": [] if bk == "lx-inc" else ["lx-inc"], "prefixes": sorted(p for p, b in L.BOOKS if b == bk),
               "profile": "lx-gnuc", "producer": {"ctags": L.CTAGS, "ctags_sha256": L.sha_file(L.CTAGS), "version": "Universal Ctags 5.9.0"},
               "H": H, "files": fs, "file_count": len(fs), "bytes": sum(L.manifest()[p]["bytes"] for p in fs),
               "symbols": sum(1 for _ in open(os.path.join(d, "symbols.jsonl"))), "router_nodes": len(nm),
               "files_sha256": {n: L.sha_file(os.path.join(d, n + ".jsonl")) for n in ("symbols", "anchors", "idmap", "nodemap")},
               "tools_sha256": tools}
        out[f"hb/{bk}/book/manifest.json"] = L.canon(man)
    if len(Hs) != 1:
        raise L.LxError("E_H_NOT_CORPUS_WIDE", str(sorted(map(str, Hs))))
    ok, det = check_partition(files, parts)
    if not ok:
        raise L.LxError("E_PARTITION", det)
    return out


def main():
    files = build()
    if "--check" in sys.argv:
        bad = [k for k, v in sorted(files.items()) if not os.path.exists(os.path.join(L.X, k)) or open(os.path.join(L.X, k), "rb").read() != v]
        print(json.dumps({"check": "byte-identical" if not bad else "DIFFERENT", "bad": bad}))
        return 1 if bad else 0
    for k, v in sorted(files.items()):
        L.write_bytes(os.path.join(L.X, k), v)
    print(json.dumps({k.split("/")[1]: json.loads(v)["file_count"] for k, v in sorted(files.items())}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
