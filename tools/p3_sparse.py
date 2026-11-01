# p3_sparse.py — draft spec/SPARSE.patterns (no-cone, gitignore syntax) from the §2.3 tiers, plus a
# last-match-wins probe. DRAFT [TARGET]: BT-SEL-1 regenerates the file from the tree API. stdlib only.
import hashlib, re
def top_only(d): return [f"/{d}/*", f"!/{d}/*/"]            # files directly in d, no subdirs
def dirs(base, names): return [f"/{base}/{n}/" for n in names]
P = ["# T0-L root files (COPYING, MAINTAINERS, Makefile, Kconfig, ...) + licences + usr", "/*", "!/*/",
     "/LICENSES/", "/usr/",
     "# T0-S core", "/kernel/"] + [f"!/kernel/{x}/" for x in ("trace", "bpf", "kcsan", "gcov", "livepatch", "liveupdate")] + \
    ["/mm/"] + [f"!/mm/{x}/" for x in ("damon", "kasan", "kmsan", "kfence")] + \
    ["/virt/", "/ipc/", "/init/",
     "# T0-S arch (top-level Kconfig/Makefile kept by the top_only pair, L5-63)"] + \
    top_only("arch/arm64") + dirs("arch/arm64", ("kernel", "kvm", "mm", "include", "lib")) + \
    top_only("arch/x86") + dirs("arch/x86", ("kernel", "kvm", "include", "mm", "boot", "lib", "entry", "realmode", "coco", "virt")) + \
    ["# T0-S fs, lib"] + top_only("fs") + dirs("fs", ("proc", "sysfs", "kernfs", "ramfs")) + top_only("lib") + \
    ["# T0-S drivers (single files need no-cone)", "/drivers/virtio/"] + \
    [f"/drivers/irqchip/{f}" for f in ("irq-gic.c", "irq-gic-common.c", "irq-gic-v2m.c", "irq-gic-v3.c", "irq-gic-v3-its.c",
                                       "irq-gic-v4.c", "irq-gic-v5.c", "irq-gic-v5-irs.c", "irq-gic-v5-its.c",
                                       "irq-gic-v5-iwb.c", "irqchip.c")] + \
    ["# irqchip: 2 .h names ABSENT here; BT-SEL-1 emits them from the tree API"] + \
    [f"/drivers/clocksource/{f}" for f in ("arm_arch_timer.c", "arm_arch_timer_mmio.c", "i8253.c", "timer-of.c", "timer-of.h")] + \
    ["/drivers/block/virtio_blk.c", "/drivers/char/virtio_console.c", "/drivers/net/virtio_net.c", "/drivers/tty/hvc/",
     "/drivers/tty/serial/amba-pl011.c", "/drivers/tty/serial/8250/8250_core.c",
     "# T0-I header pool (fetched whole; only the closure is symbol-routed)"] + \
    dirs("include", ("linux", "uapi", "asm-generic", "trace", "vdso")) + \
    ["# T1-F file level", "/block/", "/io_uring/", "/security/", "/crypto/"] + \
    dirs("fs", ("9p", "fuse", "overlayfs", "erofs", "squashfs", "ext4")) + \
    dirs("Documentation", ("RCU", "locking", "scheduler", "mm", "virt", "core-api", "arch/arm64", "arch/x86"))

def rx(p):
    body = p.lstrip("!").strip("/")
    return re.compile("^" + re.escape(body).replace(r"\*", "[^/]+") + "$")
RULES = [(p.startswith("!"), p.endswith("/"), rx(p)) for p in P if not p.startswith("#")]
def kept(path):
    parts = path.split("/"); res = False
    for neg, dir_only, r in RULES:
        cands = ["/".join(parts[:i]) for i in range(1, len(parts))] + ([] if dir_only else [path])
        if any(r.match(c) for c in cands): res = not neg
    return res
text = "\n".join(P) + "\n"
print(f"patterns={len(RULES)} comment_lines={len(P)-len(RULES)} sha256={hashlib.sha256(text.encode()).hexdigest()[:16]}")
PROBES = [("COPYING", 1), ("MAINTAINERS", 1), ("kernel/sched/core.c", 1), ("kernel/trace/trace.c", 0),
          ("mm/kasan/common.c", 0), ("arch/arm64/Kconfig", 1), ("arch/arm64/kernel/head.S", 1),
          ("arch/arm64/boot/dts/arm/foo.dts", 0), ("arch/x86/kernel/head_64.S", 1), ("arch/x86/events/core.c", 0),
          ("fs/exec.c", 1), ("fs/proc/base.c", 1), ("fs/xfs/xfs_inode.c", 0), ("fs/ext4/inode.c", 1),
          ("lib/rbtree.c", 1), ("lib/crypto/sha256.c", 0), ("drivers/net/virtio_net.c", 1),
          ("drivers/net/ethernet/intel/e1000/e1000_main.c", 0), ("drivers/irqchip/irq-gic-v3.c", 1),
          ("drivers/irqchip/irq-bcm2835.c", 0), ("include/linux/sched.h", 1), ("include/dt-bindings/clock/x.h", 0),
          ("Documentation/RCU/whatisRCU.rst", 1), ("Documentation/admin-guide/README.rst", 0), ("rust/kernel/lib.rs", 0)]
bad = 0
for p, want in PROBES:
    got = kept(p); bad += got != bool(want)
    print(f"{'ok ' if got == bool(want) else 'BAD'} {'KEEP' if got else 'drop'} {p}")
print(f"probes={len(PROBES)} mismatches={bad}")
raise SystemExit(1 if bad else 0)
