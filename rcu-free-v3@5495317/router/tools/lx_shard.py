#!/usr/bin/env python3
"""lx_shard.py - BT-LXR-11: router shard packer and unpacker (section 5.9, lx.shard.v1).

usage: lx_shard.py pack [--out DIR]          writes DIR (default X/dist/router)/{lx-files,lx-<book> x13}.tar.zst,
                                             SHA256SUMS, shards.jsonl
       lx_shard.py unpack SHARD DEST [--sums SHA256SUMS]
Deterministic tar (sorted entries, mtime 0, uid/gid 0, empty owner names, modes 0644/0755, GNU format), compressed
with /usr/bin/zstd -9 single-threaded [TARGET-CHOSEN level]. Every shard carries its own MANIFEST.jsonl (path, bytes,
sha256 of each member), SHA256SUMS, index/ID, COPYING, LICENSES/ and PROVENANCE.json (R-L3).
Unpack verifies the shard sha256 against SHA256SUMS and the member hashes; any mismatch, truncation or decode error
is E_CHUNK_SHA (rc 5); members with absolute or '..' paths are refused.
"""
import io, json, os, subprocess, sys, tarfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lxlib as L  # noqa: E402

ZSTD = "/usr/bin/zstd"
LEVEL = "-9"


class ChunkError(Exception):
    pass


def tree(base, rel):
    out = []
    root = os.path.join(base, rel)
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            out.append((os.path.relpath(p, base).replace(os.sep, "/"), p))
    return out


def shard_members(name):
    if name == "lx-files":
        m = [(f"nodes/{f}", os.path.join(L.X, "nodes", f)) for f in sorted(os.listdir(os.path.join(L.X, "nodes")))]
        m += [("routes/lx.tsv", os.path.join(L.X, "routes", "lx.tsv"))] + tree(L.X, "index/lx")
    else:
        m = tree(L.X, f"hb/{name}/book") + tree(L.X, f"index/{name}")
    m += [("COPYING", os.path.join(L.SRC, "COPYING")), ("PROVENANCE.json", os.path.join(L.META, "PROVENANCE.json"))]
    m += tree(L.SRC, "LICENSES")
    return sorted(m)


def tar_bytes(entries):
    """entries: [(arcname, bytes)] -> deterministic tar bytes."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as t:
        dirs = sorted({"/".join(a.split("/")[:i]) for a, _ in entries for i in range(1, a.count("/") + 1)})
        for d in dirs:
            ti = tarfile.TarInfo(d)
            ti.type, ti.mode, ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname = tarfile.DIRTYPE, 0o755, 0, 0, 0, "", ""
            t.addfile(ti)
        for a, b in entries:
            ti = tarfile.TarInfo(a)
            ti.size, ti.mode, ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname = len(b), 0o644, 0, 0, 0, "", ""
            t.addfile(ti, io.BytesIO(b))
    return buf.getvalue()


def zstd(b, decompress=False):
    argv = [ZSTD, "-q", "-c", "--no-progress"] + (["-d"] if decompress else [LEVEL, "-T1"])
    p = subprocess.run(argv, input=b, capture_output=True, env=L.ENV)
    if p.returncode != 0:
        raise ChunkError(p.stderr.decode("utf-8", "replace")[:200])
    return p.stdout


def pack(out):
    ixid = L.fresh_id()
    names = ["lx-files"] + L.BOOK_IDS
    recs, sums = [], []
    for n in names:
        ents = [(a, open(p, "rb").read()) for a, p in shard_members(n)]
        man = L.jsonl_bytes([{"path": a, "bytes": len(b), "sha256": L.sha256b(b)} for a, b in ents])
        inner = "".join(f"{L.sha256b(b)}  {a}\n" for a, b in ents).encode()
        ents += [("MANIFEST.jsonl", man), ("SHA256SUMS", inner), ("index/ID", (ixid + "\n").encode())]
        ents.sort()
        z = zstd(tar_bytes(ents))
        fn = f"{n}.tar.zst"
        L.write_bytes(os.path.join(out, fn), z)
        h = L.sha256b(z)
        sums.append(f"{h}  {fn}\n")
        recs.append({"schema": "lx.shard.v1", "shard": fn, "package": L.PACKAGE, "commit": L.PIN, "tree": L.TREE, "index_id": ixid,
                     "bytes": len(z), "sha256": h, "files": len(ents), "licence_files": ["COPYING", "LICENSES/", "PROVENANCE.json"]})
    L.write_bytes(os.path.join(out, "SHA256SUMS"), "".join(sums).encode())
    L.write_jsonl(os.path.join(out, "shards.jsonl"), recs)
    return recs


def unpack(shard, dest, sums=None):
    """-> list of extracted member paths; raises ChunkError (E_CHUNK_SHA)."""
    raw = open(shard, "rb").read()
    sums = sums or os.path.join(os.path.dirname(shard), "SHA256SUMS")
    want = {l.split("  ", 1)[1]: l.split("  ", 1)[0] for l in open(sums).read().splitlines()}
    if want.get(os.path.basename(shard)) != L.sha256b(raw):
        raise ChunkError(f"E_CHUNK_SHA: {os.path.basename(shard)} sha256 mismatch")
    try:
        t = tarfile.open(fileobj=io.BytesIO(zstd(raw, decompress=True)), mode="r:")
        files = {}
        for m in t.getmembers():
            if m.name.startswith("/") or ".." in m.name.split("/"):
                raise ChunkError(f"E_CHUNK_SHA: unsafe member {m.name}")
            if m.isfile():
                files[m.name] = t.extractfile(m).read()
    except (tarfile.TarError, ChunkError) as e:
        raise ChunkError(f"E_CHUNK_SHA: {e}")
    inner = {l.split("  ", 1)[1]: l.split("  ", 1)[0] for l in files["SHA256SUMS"].decode().splitlines()}
    for a, h in inner.items():
        if a not in files or L.sha256b(files[a]) != h:
            raise ChunkError(f"E_CHUNK_SHA: member {a}")
    for a, b in files.items():
        if a == "index/ID" or a in ("MANIFEST.jsonl", "SHA256SUMS"):
            continue               # shard-level metadata; the per-index ID files travel inside index/<dir>/
        L.write_bytes(os.path.join(dest, a), b)
    return sorted(files)


def main():
    a = sys.argv[1:]
    if a and a[0] == "pack":
        out = a[a.index("--out") + 1] if "--out" in a else os.path.join(L.X, "dist", "router")
        recs = pack(out)
        print(json.dumps({"shards": len(recs), "bytes": sum(r["bytes"] for r in recs), "index_id": recs[0]["index_id"],
                          "compressor": "zstd " + subprocess.run([ZSTD, "--version"], capture_output=True, text=True).stdout.strip()}))
        return 0
    if a and a[0] == "unpack":
        sums = a[a.index("--sums") + 1] if "--sums" in a else None
        try:
            print(json.dumps({"members": len(unpack(a[1], a[2], sums))}))
        except ChunkError as e:
            print(str(e))
            return 5
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
