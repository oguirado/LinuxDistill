#!/usr/bin/env python3
"""BT-LXR-05 gate: closure recomputed twice is equal (and equal to disk), size and ABSENT share are reported, and no
generated header (CL-3) is ever resolved to a file. must-FAIL: a synthetic includes.json where generated/autoconf.h
resolves to a real path."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gatelib import X, main
import lxlib as L
import lx_includes as I


def cl3(doc):
    bad = [e for e in doc["edges"] if (e[1].startswith("generated/") or "/generated/" in e[1]) and e[2] is not None]
    nonpool = [e for e in doc["edges"] if e[2] is not None and e[2] not in L.manifest()]
    return bad, nonpool


def positive():
    a, b = I.build(), I.build()
    disk = {k: open(os.path.join(X, k), "rb").read() for k in a}
    doc = json.loads(disk["graph/includes.json"])
    bad, nonpool = cl3(doc)
    rep = json.loads(disk["closure/report.json"])
    ok = a == b == disk and not bad and not nonpool and rep["closure_kept_files"] > 0 and "absent_share_ppm" in rep
    return ok, (f"twice_equal={a == b} disk_equal={a == disk} generated_resolved={len(bad)} target_outside_pool={len(nonpool)} "
                f"closure_files={rep['closure_kept_files']} closure_MB={rep['closure_kept_bytes'] / 1e6:.2f} absent_ppm={rep['absent_share_ppm']}")


def must_fail():
    doc = L.jload(os.path.join(X, "fixtures", "lx", "includes", "generated_resolved.json"))
    bad, _ = cl3(doc)
    return not bad, f"generated_resolved={len(bad)}"


if __name__ == "__main__":
    main(positive, must_fail)
