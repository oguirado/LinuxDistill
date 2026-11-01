# lx_meta.py — provenance, MANIFEST and gates A2..A5 for one pinned lx snapshot. stdlib only, no network.
# usage: lx_meta.py selftest <empty-scratch-dir>      (the real run is driven by tools/lx_acquire.sh, §3.4)
import hashlib, json, os, sys
SPDX_LINES = 3                                   # [TARGET] SPDX must sit in the first 3 lines
LANG = {".c": "c", ".h": "c-header", ".S": "asm", ".rs": "rust", ".rst": "rst", ".txt": "text", ".py": "python"}
def git_blob(b): return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()
def walk(src):
    out = []
    for d, _, fs in os.walk(src):
        for f in fs:
            p = os.path.join(d, f); out.append(os.path.relpath(p, src).replace(os.sep, "/"))
    return sorted(out)
def spdx(b):
    for ln in b.split(b"\n")[:SPDX_LINES]:
        i = ln.find(b"SPDX-License-Identifier:")
        if i >= 0:
            v = ln[i + 24:].decode("utf-8", "replace").strip().rstrip("*/").strip()
            return v
    return "ABSENT"
def tier_of(path, tiers):                        # longest prefix wins; tiers = [(prefix, tier)]
    best = max((p for p, _ in tiers if path == p or path.startswith(p.rstrip("/") + "/") or p == ""), key=len, default=None)
    return dict(tiers).get(best, "UNTIERED")
def manifest(src, tiers):
    rows = []
    for p in walk(src):
        b = open(os.path.join(src, p), "rb").read(); s = spdx(b)
        rows.append({"path": p, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(), "git_blob": git_blob(b),
                     "tier": tier_of(p, tiers), "spdx": s,
                     "spdx_exception": "Linux-syscall-note" if "Linux-syscall-note" in s else None,
                     "lang": LANG.get(os.path.splitext(p)[1], "other")})
    return rows
def gates(rows, lsfiles, spdx_exempt, expect, forbid, drivers_allow):
    ls = {}
    for ln in lsfiles.splitlines():
        meta, path = ln.split("\t", 1); ls[path] = meta.split()[1]
    r = {}
    r["A2"] = sorted(x["path"] for x in rows if ls.get(x["path"]) != x["git_blob"]) + sorted(set(ls) - {x["path"] for x in rows})
    r["A3"] = sorted(x["path"] for x in rows if x["spdx"] == "ABSENT" and x["path"] not in spdx_exempt)
    got = (len(rows), sum(x["bytes"] for x in rows))
    r["A4"] = [] if got == expect else [f"got files={got[0]} bytes={got[1]} expected files={expect[0]} bytes={expect[1]}"]
    r["A5"] = sorted(x["path"] for x in rows if any(x["path"].startswith(f) for f in forbid)
                     or (x["path"].startswith("drivers/") and not any(x["path"].startswith(a) for a in drivers_allow)))
    return r
def selftest(base):
    src = os.path.join(base, "src"); os.makedirs(src)
    files = {  # synthetic stand-ins written by us (RL-6: no Linux text), mimicking the shapes A2..A5 inspect
        "COPYING": b"synthetic licence notice\n",
        "kernel/sched/demo.c": b"// SPDX-License-Identifier: GPL-2.0-only\nint demo(void) { return 0; }\n",
        "include/uapi/linux/demo.h": b"/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */\n#define DEMO_NR 1\n",
        "drivers/virtio/demo_ring.c": b"// SPDX-License-Identifier: GPL-2.0-or-later\nint ring;\n",
        "lib/empty.c": b"",
    }
    for p, b in files.items():
        os.makedirs(os.path.dirname(os.path.join(src, p)) or src, exist_ok=True)
        open(os.path.join(src, p), "wb").write(b)
    tiers = [("", "T0-L"), ("kernel/", "T0-S"), ("include/", "T0-I"), ("drivers/virtio/", "T0-S"), ("lib/", "T0-S")]
    rows = manifest(src, tiers)
    for x in rows:
        print(json.dumps({k: x[k] for k in ("path", "bytes", "git_blob", "tier", "spdx", "spdx_exception", "lang")}, sort_keys=True))
    print("empty-blob id matches git's well-known id:", git_blob(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")
    ls = "".join(f"100644 {x['git_blob']} 0\t{x['path']}\n" for x in rows)
    exp = (len(rows), sum(x["bytes"] for x in rows))
    args = ({"COPYING", "lib/empty.c"}, exp, ("arch/arm64/boot/dts/",), ("drivers/virtio/",))
    print("clean   :", json.dumps(gates(rows, ls, *args), sort_keys=True))
    open(os.path.join(src, "kernel/sched/demo.c"), "ab").write(b"/* tampered */\n")   # must-FAIL fixture
    os.makedirs(os.path.join(src, "drivers/net")); open(os.path.join(src, "drivers/net/x.c"), "wb").write(b"int x;\n")
    bad = gates(manifest(src, tiers), ls, *args)
    print("tampered:", json.dumps(bad, sort_keys=True))
    return all(bad[k] for k in ("A2", "A3", "A4", "A5"))
if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "selftest":
        sys.exit(0 if selftest(sys.argv[2]) else 1)
    sys.exit("usage: lx_meta.py selftest <empty-scratch-dir>")
