#!/usr/bin/env python3
"""BT-LXR-01 gate: each macro line's 1-line synthetic sample emits the expected tag (positive);
the SYSCALL_DEFINE3 sample with the table removed must FAIL (it emits tag SYSCALL_DEFINE3)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gatelib import X, main
import lxlib as L

FX = os.path.join(X, "fixtures", "lx", "macros")


def check(rows, macros):
    tags = L.run_ctags(sorted({r["file"] for r in rows}), macros=macros, cwd=FX)
    got = {(t["path"], t["name"], t["kind"], t.get("typeref")) for t in tags}
    bad = [r for r in rows if not any(g[0] == r["file"] and g[1] == r["name"] and g[2] == r["kind"]
                                      and ("typeref" not in r or g[3] == r["typeref"]) for g in got)]
    names = sorted({t["name"] for t in tags if t["path"] in {b["file"] for b in bad}})
    return (not bad), f"rows={len(rows)} missing={len(bad)} emitted_for_missing={names[:4]}"


def rows():
    with open(os.path.join(FX, "expected.jsonl")) as f:
        return [json.loads(l) for l in f]


def positive():
    return check(rows(), L.MACROS)


def must_fail():
    return check([r for r in rows() if r["file"] == "SYSCALL_DEFINE3.c"], None)


if __name__ == "__main__":
    main(positive, must_fail)
