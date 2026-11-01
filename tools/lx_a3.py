#!/usr/bin/env python3
"""lx_a3.py - gate A3 ruling for corpus lx (LX §3.5 A3, §4): a file without an SPDX line inherits the tree-wide licence
declared by the root COPYING ("SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note"); LICENSES/* are licence texts.
Every lx file is STUDY-only under the STRICT clean room (R-L1), so A3 labels provenance; it never admits copying.
usage: lx_a3.py <pin dir>  -> writes meta/A3.json; rc 0 iff no file is left without an effective licence"""
import json, os, re, sys

d = sys.argv[1]
rows = [json.loads(l) for l in open(os.path.join(d, "meta/MANIFEST.jsonl"))]
cop = open(os.path.join(d, "src/COPYING"), encoding="utf-8").read()
m = re.search(r"SPDX-License-Identifier:\s*(.+)", cop)
root = m.group(1).strip() if m else None
out, unresolved = {"declared": 0, "inherited_copying": [], "licence_text": []}, []
for r in rows:
    if r["spdx"] != "ABSENT":
        out["declared"] += 1
    elif r["path"].startswith("LICENSES/") or r["path"] == "COPYING":
        out["licence_text"].append(r["path"])
    elif root:
        out["inherited_copying"].append(r["path"])
    else:
        unresolved.append(r["path"])
res = {"schema": "lx.a3.v1", "root_licence": root, "rule": "ABSENT SPDX -> root COPYING licence; LICENSES/* = licence texts",
       "zone": "Z-STUDY STRICT (all lx files)", "declared": out["declared"], "inherited": len(out["inherited_copying"]),
       "licence_text": len(out["licence_text"]), "unresolved": unresolved, "inherited_paths": out["inherited_copying"],
       "pass": not unresolved}
json.dump(res, open(os.path.join(d, "meta/A3.json"), "w"), indent=1, sort_keys=True)
print(json.dumps({k: res[k] for k in ("root_licence", "declared", "inherited", "licence_text", "pass")}))
sys.exit(0 if res["pass"] else 5)
