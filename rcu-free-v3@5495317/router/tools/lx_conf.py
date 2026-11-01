#!/usr/bin/env python3
"""lx_conf.py - BT-LXR-10: generate and score the G-LX-CONF conformance fixture (section 5.10).

usage: lx_conf.py gen      writes X/fixtures/lx/conf/rows.jsonl and X/fixtures/score_ref_lx.json
       lx_conf.py score    scores the built router against them (rc 0 only if every row PASSES)
Gold answers are derived mechanically with GNU grep over src/ (gates/xcheck.py), independently of ctags and of the
router's own lexer; each row stores only the evidence coordinates (path:line, file counts), never source text.
Row classes: FIND (12, one per non-include book), IMPACT (6, grep -nw caller sets of file-static functions),
ARCHPAIR (4), KCONFIG (4, Makefile `obj-$(CONFIG_X) += f.o` lines), ABSENT (6). A returned sid must full-match the
hb.defs.v2 pattern and never carry a ctags __anon id.
"""
import json, os, re, sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gates"))
import lxlib as L  # noqa: E402
import lx_calls as C  # noqa: E402
import lx_query as Q  # noqa: E402
import xcheck as XC  # noqa: E402

CONF = os.path.join(L.X, "fixtures", "lx", "conf", "rows.jsonl")
REF = os.path.join(L.X, "fixtures", "score_ref_lx.json")
FIND = [("__schedule", "kernel/sched/core.c"), ("synchronize_rcu", "kernel/rcu/tree.c"), ("mutex_lock", "kernel/locking/mutex.c"),
        ("hrtimer_start_range_ns", "kernel/time/hrtimer.c"), ("handle_irq_event", "kernel/irq/handle.c"),
        ("kernel_clone", "kernel/fork.c"), ("handle_mm_fault", "mm/memory.c"), ("kvm_vcpu_ioctl", "virt/kvm/kvm_main.c"),
        ("vectors", "arch/arm64/kernel/entry.S"), ("entry_SYSCALL_64", "arch/x86/entry/entry_64.S"),
        ("virtqueue_add_split", "drivers/virtio/virtio_ring.c"), ("start_kernel", "init/main.c")]
IMPACT_BOOKS = ["lx-sched", "lx-mm", "lx-kvm", "lx-kcore", "lx-dev", "lx-boot"]
ARCH_CAND = ["arch_cpu_idle", "machine_restart", "setup_arch", "kvm_arch_vcpu_ioctl_run", "arch_show_interrupts",
             "machine_power_off", "arch_cpu_finalize_init", "kvm_arch_init_vm", "__switch_to", "cpu_die_early"]
GPU_SYMS = ["drm_gem_object_init", "amdgpu_device_init"]
GEN_HDRS = ["include/generated/autoconf.h", "include/generated/asm-offsets.h"]


def def_lines(name, path):
    """grep -nw name path, kept when the line looks like a definition start (C: identifier at column 0, '(' after
    the name, no trailing ';'; asm: SYM_*START*(name) / ENTRY(name))."""
    if path.endswith(".S"):
        pat = re.compile(r"^\s*(SYM_\w*START\w*|ENTRY)\(\s*" + re.escape(name) + r"\s*\)")
    else:
        pat = re.compile(r"^[A-Za-z_].*\b" + re.escape(name) + r"\s*\(.*[^;]\s*$")
    out = []
    for l in XC.grep(["-nw", "--", name, path]):
        n, t = l.split(":", 1)
        if pat.match(t):
            out.append(int(n))
    return out


def arch_def_files(name, arch):
    files = XC.grep(["-rlw", "--include=*.c", "--include=*.S", "--", name, f"arch/{arch}"])
    return sorted(f for f in files if def_lines(name, f))


def gen_rows():
    rows = []
    for name, path in FIND:
        dl = def_lines(name, path)
        if dl:
            rows.append({"id": f"FIND-{len(rows) + 1:02d}", "class": "find", "q": name, "gold": {"sid": f"{path}::{name}"},
                         "evidence": {"cmd": f"grep -nw {name} {path}", "def_lines": dl}})
    syms = C.load_symbols()
    for s, gold in XC.pick_static(syms, IMPACT_BOOKS, per_book=1):
        rows.append({"id": f"IMPACT-{len(rows) + 1:02d}", "class": "impact", "q": s["sid"], "gold": {"callers": gold},
                     "evidence": {"cmd": f"grep -rlw {s['name']} (only {s['path']}); grep -nw {s['name']} {s['path']}", "callers": len(gold)}})
    n = 0
    for name in ARCH_CAND:
        a, x = arch_def_files(name, "arm64"), arch_def_files(name, "x86")
        if len(a) == 1 and len(x) == 1 and n < 4:
            rows.append({"id": f"ARCHPAIR-{len(rows) + 1:02d}", "class": "archpair", "q": name,
                         "gold": {"pair": [f"{a[0]}::{name}", f"{x[0]}::{name}"]},
                         "evidence": {"cmd": f"grep -rlw {name} arch/arm64 arch/x86 + definition regex", "arm64": a, "x86": x}})
            n += 1
    mk = XC.grep(["-rnE", r"^obj-\$\(CONFIG_[A-Z0-9_]+\)\s*\+=\s*[a-z0-9_]+\.o\s*$", "--include=Makefile", "drivers"])
    n = 0
    for l in sorted(mk):
        f, ln, t = l.split(":", 2)
        cfg = re.search(r"CONFIG_[A-Z0-9_]+", t).group(0)
        obj = re.search(r"([a-z0-9_]+)\.o", t.split("+=")[1]).group(1)
        src = f.rsplit("/", 1)[0] + "/" + obj + ".c"
        src = src[2:] if src.startswith("./") else src
        if src in L.manifest() and n < 4:
            rows.append({"id": f"KCONFIG-{len(rows) + 1:02d}", "class": "kconfig", "q": cfg, "gold": {"built_by": src},
                         "evidence": {"cmd": "grep -rnE '^obj-$(CONFIG_X) += f.o$' --include=Makefile drivers", "line": f"{f}:{ln}"}})
            n += 1
    for name in GPU_SYMS:
        if not XC.grep(["-rlw", "--", name, "."]):
            rows.append({"id": f"ABSENT-{len(rows) + 1:02d}", "class": "find", "q": name, "gold": {"status": "ABSENT"},
                         "evidence": {"cmd": f"grep -rlw {name} . (0 files; drivers/gpu is OUT of the pool)"}})
    n = 0
    for s in sorted((s for s in syms if s["book"] == "lx-x86" and s["ckind"] == "function" and s["router"] and "." not in s["qual"]), key=lambda s: s["sid"]):
        if n >= 2:
            break
        fs = XC.grep_files(s["name"])
        if fs and all(f.startswith("arch/x86/") for f in fs):
            rows.append({"id": f"ABSENT-{len(rows) + 1:02d}", "class": "find", "book": "lx-a64", "q": s["name"], "gold": {"status": "ABSENT"},
                         "evidence": {"cmd": f"grep -rlw {s['name']} . (all {len(fs)} hits under arch/x86/)"}})
            n += 1
    for h in GEN_HDRS:
        if h not in L.manifest():
            rows.append({"id": f"ABSENT-{len(rows) + 1:02d}", "class": "where", "q": h, "gold": {"status": "ABSENT"},
                         "evidence": {"cmd": f"{h} not in meta/MANIFEST.jsonl (generated header, OD-LX-PREPARE)"}})
    return rows


def sid_ok(s):
    return bool(L.SID_RE.fullmatch(s)) and "__anon" not in s


def ans_sids(a):
    out = []
    for r in a.get("rows", []):
        if isinstance(r, list):
            out += [x for x in r if isinstance(x, str) and "::" in x]
        elif isinstance(r, dict):
            for v in r.values():
                if isinstance(v, str) and "::" in v:
                    out.append(v)
                elif isinstance(v, list):
                    out += [x for x in v if isinstance(x, str) and "::" in x]
    return out


def judge(row, a):
    try:
        return _judge(row, a)
    except (KeyError, IndexError, TypeError):
        return False


def _judge(row, a):
    if not all(sid_ok(s) for s in ans_sids(a)):
        return False
    g, st = row["gold"], a.get("status")
    if "status" in g:
        return st == "ABSENT" and not a.get("rows")
    if st != "OK":
        return False
    if row["class"] == "find":
        return any(r[0] == g["sid"] or r[0].startswith(g["sid"] + ".alt_") for r in a["rows"])
    if row["class"] == "impact":
        return a["rows"][0]["callers"] == g["callers"]
    if row["class"] == "archpair":
        return g["pair"] in a["rows"]
    if row["class"] == "kconfig":
        return g["built_by"] in a["rows"][0]["built_by"]
    return False


def score(router, rows, ref=None):
    res = []
    for row in rows:
        rc, a = router.run(row["class"], row["q"], row.get("book"))
        ok = judge(row, a)
        sha = Q.answer_sha(a)
        if ref is not None:
            ok = ok and ref["answers"].get(row["id"]) == sha
        res.append((row["id"], ok, sha))
    return res


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"
    if cmd == "gen":
        rows = gen_rows()
        L.write_jsonl(CONF, rows)
        r = Q.Router()
        res = score(r, rows)
        ref = {"schema": "lx.score-ref.v1", "gate_id": "G-LX-CONF", "index_id": L.fresh_id(), "rows": len(rows),
               "per_class": {c: sum(1 for x in rows if x["id"].startswith(c)) for c in ("FIND", "IMPACT", "ARCHPAIR", "KCONFIG", "ABSENT")},
               "expected": {i: "PASS" for i, _, _ in res}, "answers": {i: s for i, _, s in res},
               "blocked": {"KCONFIG CONFIG_VIRTIO_BLK": "drivers/block/Makefile not in the sparse pool",
                           "ABSENT-with-coordinates T2-R": "no T2-R catalogue rows (path, bytes, blob) on disk"},
               "thin_dev": True}
        L.write_json(REF, ref)
        print(json.dumps({"rows": len(rows), "pass_at_gen": sum(ok for _, ok, _ in res), "fail_ids": [i for i, ok, _ in res if not ok], "per_class": ref["per_class"]}))
        return 0
    rows = L.read_jsonl(CONF)
    ref = L.jload(REF)
    res = score(Q.Router(), rows, ref)
    print(json.dumps({"rows": len(rows), "pass": sum(ok for _, ok, _ in res), "fail_ids": [i for i, ok, _ in res if not ok]}))
    return 0 if len(rows) >= 30 and all(ok for _, ok, _ in res) else 1


if __name__ == "__main__":
    sys.exit(main())
