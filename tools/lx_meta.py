#!/usr/bin/env python3
"""lx_meta.py - BT-LX-01 provenance, MANIFEST and gates A2..A5 (LX §3.6 functions, imported verbatim from lx_meta_ref.py).
usage: lx_meta.py provenance D SHA TREE | manifest D | gates D      (run by tools/lx_acquire.sh)"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lx_meta_ref as R  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIERS = [("", "T0-L"), ("LICENSES/", "T0-L"), ("usr/", "T0-L"), ("include/", "T0-I")] + \
    [(p, "T0-S") for p in ("kernel/", "mm/", "virt/", "ipc/", "init/", "arch/", "fs/", "lib/", "drivers/")] + \
    [(p, "T1-F") for p in ("block/", "io_uring/", "security/", "crypto/", "Documentation/", "fs/9p/", "fs/fuse/", "fs/overlayfs/",
                           "fs/erofs/", "fs/squashfs/", "fs/ext4/")]
DRIVERS_ALLOW = ("drivers/virtio/", "drivers/irqchip/", "drivers/clocksource/", "drivers/block/virtio_blk.c",
                 "drivers/char/virtio_console.c", "drivers/net/virtio_net.c", "drivers/tty/hvc/",
                 "drivers/tty/serial/amba-pl011.c", "drivers/tty/serial/8250/8250_core.c")
FORBID = ("arch/arm64/boot/dts/",)


def main(a):
    if a[1] == "provenance":
        d, sha, tree = a[2:5]
        git = lambda *x: subprocess.check_output(["git", "-C", os.path.join(d, "src")] + list(x), text=True).strip()
        print(json.dumps({"schema": "lx.provenance.v1", "repo": "https://github.com/torvalds/linux.git", "commit": git("rev-parse", "HEAD"),
                          "tree": git("rev-parse", "HEAD^{tree}"), "pin_commit": sha, "pin_tree": tree,
                          "committer_date": git("log", "-1", "--format=%cI"), "subject": git("log", "-1", "--format=%s"),
                          "git_version": subprocess.check_output(["git", "--version"], text=True).strip(),
                          "patterns_sha256": R.hashlib.sha256(open(os.path.join(ROOT, "spec/SPARSE.patterns"), "rb").read()).hexdigest()},
                         indent=1, sort_keys=True))
        return 0
    d = a[2]; src = os.path.join(d, "src")
    if a[1] == "manifest":
        for x in R.manifest(src, TIERS):
            print(json.dumps(x, sort_keys=True))
        return 0
    if a[1] == "gates":
        rows = [json.loads(l) for l in open(os.path.join(d, "meta/MANIFEST.jsonl"))]
        exp = json.load(open(os.path.join(ROOT, "spec/EXPECT.json")))
        exempt = {x["path"] for x in rows if "/" not in x["path"] or x["path"].startswith("LICENSES/")}
        g = R.gates(rows, open(os.path.join(d, "meta/ls-files.txt")).read(), exempt, (exp["files"], exp["bytes"]), FORBID, DRIVERS_ALLOW)
        paths = sorted(x["path"] for x in rows)
        g["A4_paths_equal"] = R.hashlib.sha256("\n".join(paths).encode()).hexdigest() == exp["paths_sha256"]
        out = {"schema": "lx.gates.v1", "A2": g["A2"][:50], "A2_n": len(g["A2"]), "A3_n": len(g["A3"]), "A3_sample": g["A3"][:40],
               "A4": g["A4"], "A4_paths_equal": g["A4_paths_equal"], "A5": g["A5"][:50], "A5_n": len(g["A5"]),
               "files": len(rows), "bytes": sum(x["bytes"] for x in rows)}
        print(json.dumps(out, indent=1, sort_keys=True))
        bad = out["A2_n"] or out["A4"] or not out["A4_paths_equal"] or out["A5_n"]
        return 4 if out["A2_n"] else (6 if (out["A4"] or not out["A4_paths_equal"]) else (7 if out["A5_n"] else 0))
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
