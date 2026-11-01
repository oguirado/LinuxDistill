#!/usr/bin/env python3
"""BT-LXR-06 gate. Positive: the BUILT_BY edge CONFIG_VIRTIO_MMIO -> drivers/virtio/virtio_mmio.c is present
(substitute for the paper's CONFIG_VIRTIO_BLK row, BLOCKED: drivers/block/Makefile is not in the sparse pool, and
that row is recorded as ABSENT), unresolved items are counted with coordinates, and --check is byte-identical.
must-FAIL: a synthetic `obj-$(CONFIG_X) += f.o` with no f.c in the pool must not yield the edge, and must be counted
(a silent drop would make this leg pass = DEAD)."""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gatelib import X, main
import lxlib as L
import lx_kbuild as K


def positive():
    d = L.jload(os.path.join(X, "graph", "kconfig.json"))
    edge = any(e[0] == "drivers/virtio/virtio_mmio.c" and e[1] == "CONFIG_VIRTIO_MMIO" for e in d["built_by"])
    cnt = d["unresolved"]["built_by_unknown_file"] == len(d["unresolved"]["rows"])
    absent = "CONFIG_VIRTIO_BLK" in d.get("absent", {})
    p = subprocess.run([sys.executable, "-I", "-B", os.path.join(X, "tools", "lx_kbuild.py"), "--check"], cwd="/", env=dict(L.ENV, TZ="Europe/Oslo"), capture_output=True, text=True)
    return edge and cnt and absent and p.returncode == 0, f"edge_VIRTIO_MMIO={edge} unresolved_counted={cnt} rows={len(d['unresolved']['rows'])} VIRTIO_BLK_absent_recorded={absent} check_rc={p.returncode}"


def must_fail():
    text = open(os.path.join(X, "fixtures", "lx", "kbuild", "Makefile.unknown_file")).read()
    edges, unres, _ = K.parse_makefile(text, "demo", set())
    edge = any(e[1] == "CONFIG_LX_DEMO_UNKNOWN" for e in edges)
    return edge or not unres, f"edge={edge} unresolved={unres}"


if __name__ == "__main__":
    main(positive, must_fail)
