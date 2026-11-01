#!/usr/bin/env python3
"""BT-LXR-11 gate. Positive: a second pack is byte-identical (same SHA256SUMS); every shards.jsonl record validates
lx.shard.v1 (required fields, consts, name pattern); unpacking all 14 shards into an empty root and re-running the
G-LX-CONF rows from there gives answer sha256s equal to score_ref_lx.json (FT-LX0 host leg).
must-FAIL: a truncated shard must unpack with E_CHUNK_SHA."""
import os, re, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gatelib import X, main
import lxlib as L
import lx_conf as CF
import lx_query as Q
import lx_shard as SH

DIST = os.path.join(X, "dist", "router")
NAME = re.compile(r"^lx-(files|sched|rcu|locking|time|irq|kcore|mm|kvm|a64|x86|dev|boot|inc|src-T0|src-T1|dossiers|meta)\.tar\.zst$")
REQ = ["schema", "shard", "package", "commit", "tree", "index_id", "bytes", "sha256", "files", "licence_files"]


def shard_ok(r):
    return (sorted(r) == sorted(REQ) and r["schema"] == "lx.shard.v1" and NAME.match(r["shard"]) and r["package"] == L.PACKAGE
            and r["commit"] == L.PIN and r["tree"] == L.TREE and re.fullmatch(r"[0-9a-f]{64}", r["index_id"]) and r["bytes"] >= 1
            and re.fullmatch(r"[0-9a-f]{64}", r["sha256"]) and r["files"] >= 1 and len(set(r["licence_files"])) >= 2)


def tmpdir():
    return tempfile.TemporaryDirectory(prefix="lx_shard_", dir=os.environ.get("LX_TMP"))


def positive():
    recs = L.read_jsonl(os.path.join(DIST, "shards.jsonl"))
    bad = [r["shard"] for r in recs if not shard_ok(r)]
    with tmpdir() as t:
        SH.pack(os.path.join(t, "repack"))
        same = open(os.path.join(t, "repack", "SHA256SUMS")).read() == open(os.path.join(DIST, "SHA256SUMS")).read()
        root = os.path.join(t, "root")
        for r in recs:
            SH.unpack(os.path.join(DIST, r["shard"]), root)
        rows, ref = L.read_jsonl(CF.CONF), L.jload(CF.REF)
        res = CF.score(Q.Router(root), rows, ref)
        eq = sum(ok for _, ok, _ in res)
    ok = not bad and same and len(recs) == 14 and eq == len(rows)
    return ok, f"shards={len(recs)} schema_bad={bad} repack_identical={same} requery_answer_sha_equal={eq}/{len(rows)}"


def must_fail():
    fx = L.jload(os.path.join(X, "fixtures", "lx", "shards", "truncated.json"))
    with tmpdir() as t:
        src = os.path.join(DIST, fx["shard"])
        b = open(src, "rb").read()
        dst = os.path.join(t, fx["shard"])
        open(dst, "wb").write(b[: len(b) // 2])
        try:
            SH.unpack(dst, os.path.join(t, "root"), sums=os.path.join(DIST, "SHA256SUMS"))
        except SH.ChunkError as e:
            return False, str(e)[:120]
    return True, "truncated shard unpacked without error"


if __name__ == "__main__":
    main(positive, must_fail)
