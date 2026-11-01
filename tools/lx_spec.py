#!/usr/bin/env python3
"""lx_spec.py - BT-SEL-1 (LX §2.10): spec/SPARSE.patterns from the paper's p3_sparse.py tiers, plus spec/EXPECT.json, the
kept file set measured independently from the GitHub tree API at the pinned tree (per-subtree, the recursive root listing
truncates). Network: read-only GitHub API via `gh api`. usage: lx_spec.py <ROOT>"""
import json, os, re, subprocess, sys

ROOT = sys.argv[1]
TREE = "e56d24e86147e65a8ade3cfe69dee2bfdac279fa"
IRQ_H = ["irq-gic-common.h", "irq-gic-its-msi-parent.h"]      # BT-SEL-1 fill-in: names read from the tree API at the pin
src = open(os.path.join(ROOT, "tools/p3_sparse.py"), encoding="utf-8").read()
src = src.split("\ntext = ")[0]                              # P, rx, RULES, kept: stop before the probe printout
src = src.replace('["# irqchip: 2 .h names ABSENT here; BT-SEL-1 emits them from the tree API"]',
                  repr(["/drivers/irqchip/" + h for h in IRQ_H]))
ns = {}
exec(compile(src, "p3_sparse.py", "exec"), ns)
P, kept = ns["P"], ns["kept"]
open(os.path.join(ROOT, "spec/SPARSE.patterns"), "w", encoding="utf-8").write("\n".join(P) + "\n")


def api(sha, recursive):
    q = "repos/torvalds/linux/git/trees/%s%s" % (sha, "?recursive=1" if recursive else "")
    return json.loads(subprocess.check_output(["gh", "api", q]))


files = {}


def collect(sha, prefix, depth):
    t = api(sha, recursive=depth == 0)
    if t.get("truncated"):
        if depth == 0:
            return collect(sha, prefix, 1)
        raise SystemExit("E_TRUNCATED " + prefix)
    for e in t["tree"]:
        p = prefix + e["path"]
        if e["type"] == "blob":
            files[p] = e["size"]
        elif e["type"] == "tree" and depth == 1:
            collect(e["sha"], p + "/", 0)


root = api(TREE, False)
for e in root["tree"]:
    if e["type"] == "blob":
        files[e["path"]] = e["size"]
    elif e["type"] == "tree" and any(kept(e["path"] + "/" + x) for x in ("a", "a/b", "a/b/c", "a/b/c/d")) or \
            e["type"] == "tree" and e["path"] in ("arch", "drivers", "Documentation", "fs", "include", "lib", "kernel", "mm"):
        collect(e["sha"], e["path"] + "/", 0)
k = sorted(p for p in files if kept(p))
exp = {"tree": TREE, "source": "gh api git/trees per subtree", "files": len(k), "bytes": sum(files[p] for p in k),
       "irqchip_h": IRQ_H, "paths_sha256": __import__("hashlib").sha256("\n".join(k).encode()).hexdigest()}
json.dump(exp, open(os.path.join(ROOT, "spec/EXPECT.json"), "w"), indent=1, sort_keys=True)
open(os.path.join(ROOT, "spec/EXPECT.paths"), "w").write("\n".join(k) + "\n")
print(json.dumps(exp))
