#!/usr/bin/env python3
"""BT-LXR-09 gate. Positive: a rebuild (in-process and as a subprocess with another cwd/TZ/PYTHONHASHSEED) is
byte-identical to the 14 index dirs on disk, every index/ID equals the recomputed g_lx_fresh digest, K and B are
1,200,000 and 750,000 ppm. must-FAIL: one source byte changed (in memory, pointer fixture) => the recomputed ID
must differ from index/ID, so the 'ID equal' check fails."""
import hashlib, json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gatelib import X, main
import lxlib as L
import lx_index as IX


def ids_on_disk():
    return {d: open(os.path.join(X, "index", d, "ID")).read().strip() for d in ["lx"] + L.BOOK_IDS}


def positive():
    ixid, files = IX.build()
    disk_eq = all(open(os.path.join(X, k), "rb").read() == v for k, v in files.items())
    p = subprocess.run([sys.executable, "-I", "-B", os.path.join(X, "tools", "lx_index.py"), "--check"], cwd="/", env=dict(L.ENV, TZ="Asia/Kolkata", PYTHONHASHSEED="31"), capture_output=True, text=True)
    ids = ids_on_disk()
    cols = json.loads(files["index/lx-sched/cols.json"])
    ok = disk_eq and p.returncode == 0 and set(ids.values()) == {L.fresh_id()} and cols["K"] == 1200000 and cols["B"] == 750000
    return ok, f"rebuild_identical={disk_eq} subprocess_check_rc={p.returncode} id={ixid[:16]} dirs={len(ids)} all_ids_fresh={set(ids.values()) == {L.fresh_id()}}"


def must_fail():
    fx = L.jload(os.path.join(X, "fixtures", "lx", "index", "source_byte_flip.json"))
    b = bytearray(L.src_bytes(fx["path"]))
    b[fx["byte_offset"]] ^= fx["xor"]
    sums = open(os.path.join(L.META, "SHA256SUMS"), "rb").read().decode()
    old = L.sha_file(os.path.join(L.SRC, fx["path"]))
    assert old in sums
    sums2 = sums.replace(old, hashlib.sha256(bytes(b)).hexdigest()).encode()
    rec = dict(L.fresh_record(), sha256sums=L.sha256b(sums2))
    new = L.fresh_id(rec)
    disk = ids_on_disk()["lx"]
    return new == disk, f"recomputed={new[:16]} index_ID={disk[:16]}"


if __name__ == "__main__":
    main(positive, must_fail)
