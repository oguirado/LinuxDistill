#!/usr/bin/env python3
"""lx_kbuild.py - BT-LXR-06: BUILT_BY (file -> CONFIG_X) from Makefile/Kbuild and KCONFIG nodes with DEPENDS/SELECTS.

usage: lx_kbuild.py [--check]     writes X/graph/kconfig.json
BUILT_BY: `obj-$(CONFIG_X) += f.o`, composites `f-y` / `f-objs` / `f-$(CONFIG_Y) += a.o` (a member inherits the
CONFIG of its composite plus its own). x.o resolves to x.c or x.S in the Makefile's dir; an item with no file in
the fetch pool is counted as unresolved with its coordinates, never dropped silently. Directory items are counted.
KCONFIG: `config`/`menuconfig X` entries; `depends on <expr>` -> DEPENDS to every symbol of expr; `select Y` -> SELECTS.
Implicit `if`/`menu` dependencies are not modelled [TARGET-CHOSEN].
"""
import collections, json, os, posixpath, re, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lxlib as L  # noqa: E402

ASSIGN = re.compile(r"^([A-Za-z0-9_.\-]+)-(y|m|objs|\$\(CONFIG_([A-Za-z0-9_]+)\))\s*(?::=|\+=|=)\s*(.*)$")
SKIPVAR = re.compile(r"^(ccflags|asflags|ldflags|subdir-ccflags|subdir-asflags|cflags|always|targets|extra|hostprogs|"
                     r"userprogs|clean-files|header-test|no-header-test|generic|generated|mandatory|syscall|uapi|AFLAGS|CFLAGS|KCOV|KASAN|KMSAN|KCSAN|UBSAN|OBJECT_FILES|GCOV)")
CFG = re.compile(r"^\s*(?:menu)?config\s+([A-Za-z0-9_]+)\s*$")
DEP = re.compile(r"^\s*depends\s+on\s+(.*)$")
SEL = re.compile(r"^\s*select\s+([A-Za-z0-9_]+)")
SYM = re.compile(r"\b([A-Z][A-Z0-9_]*)\b")


def logical_lines(text):
    text = text.replace("\\\n", " ")
    for ln in text.split("\n"):
        yield ln.split("#", 1)[0].strip()


def parse_makefile(text, d, pool):
    """-> (edges [(file, CONFIG, makefile_dir)], unresolved [(dir, item, CONFIG)], stats Counter)."""
    objs = []                                    # (item, cond) for obj-
    comp = collections.defaultdict(list)         # composite name -> [(member, cond)]
    st = collections.Counter()
    for ln in logical_lines(text):
        m = ASSIGN.match(ln)
        if not m:
            continue
        var, sfx, cfg, rhs = m.group(1), m.group(2), m.group(3), m.group(4)
        if SKIPVAR.match(var):
            continue
        items = [w for w in rhs.split() if w.endswith(".o") or w.endswith("/")]
        cond = f"CONFIG_{cfg}" if cfg else None
        if var in ("obj", "lib", "core", "init", "libs", "drivers", "virt"):
            objs += [(w, cond) for w in items]
        else:
            comp[var] += [(w, cond) for w in items]
    edges, unres = set(), []

    def files_for(item):
        stem = item[:-2]
        return [c for c in (posixpath.normpath(posixpath.join(d, stem + ext)) for ext in (".c", ".S")) if c in pool]

    for item, cond in objs:
        if item.endswith("/"):
            st["dir_items"] += 1
            continue
        stem = posixpath.basename(item[:-2])
        members = comp.get(stem)
        if members:
            for mi, mc in members:
                if mi.endswith("/"):
                    continue
                fs = files_for(posixpath.join(posixpath.dirname(item), mi) if "/" in item else mi)
                cfgs = [c for c in (cond, mc) if c]
                if not fs:
                    unres.append((d, mi, cond or mc or "y"))
                for f in fs:
                    for c in cfgs:
                        edges.add((f, c, d))
                    st["always" if not cfgs else "conditional"] += 1
            continue
        fs = files_for(item)
        if not fs:
            unres.append((d, item, cond or "y"))
            continue
        for f in fs:
            if cond:
                edges.add((f, cond, d))
                st["conditional"] += 1
            else:
                st["always"] += 1
    return sorted(edges), sorted(unres), st


def parse_kconfig(text, path):
    configs, deps, sels = [], [], []
    cur = None
    for i, ln in enumerate(text.split("\n"), 1):
        m = CFG.match(ln)
        if m:
            cur = "CONFIG_" + m.group(1)
            configs.append((cur, path, i))
            continue
        if re.match(r"^\s*(menu|endmenu|choice|endchoice|if|endif|comment|source|mainmenu)\b", ln):
            cur = None
            continue
        if cur is None:
            continue
        m = DEP.match(ln)
        if m:
            for s in SYM.findall(m.group(1)):
                if s not in ("y", "n", "m"):
                    deps.append((cur, "CONFIG_" + s, path))
        m = SEL.match(ln)
        if m:
            sels.append((cur, "CONFIG_" + m.group(1), path))
    return configs, deps, sels


def build():
    man = L.manifest()
    pool = set(man)
    built, unres, configs, deps, sels = set(), [], [], set(), set()
    st = collections.Counter()
    for p in sorted(man):
        b = p.rsplit("/", 1)[-1]
        d = posixpath.dirname(p)
        if b in ("Makefile", "Kbuild"):
            e, u, s = parse_makefile(L.src_bytes(p).decode("latin-1"), d, pool)
            built |= {(f, c, p) for f, c, _ in e}
            unres += [(p, item, c) for _, item, c in u]
            st.update(s)
            st["makefiles"] += 1
        elif b.startswith("Kconfig"):
            c, dp, sl = parse_kconfig(L.src_bytes(p).decode("latin-1"), p)
            configs += c
            deps |= set(dp)
            sels |= set(sl)
            st["kconfig_files"] += 1
    defined = {c for c, _, _ in configs}
    doc = {"schema": "lx.kconfig.v1", "evidence": "DERIVED lexical", "pin": L.PIN,
           "configs": sorted(configs), "built_by": sorted(built), "depends": sorted(deps), "selects": sorted(sels),
           "unresolved": {"built_by_unknown_file": len(unres), "rows": sorted(unres),
                          "built_by_config_undefined": len({c for _, c, _ in built if c not in defined}),
                          "depends_target_undefined": sum(1 for _, t, _ in deps if t not in defined),
                          "selects_target_undefined": sum(1 for _, t, _ in sels if t not in defined)},
           "stats": dict(sorted(st.items())),
           "absent": {"CONFIG_VIRTIO_BLK": "drivers/block/Makefile and drivers/block/Kconfig are not in the fetch pool (sparse selection)"}}
    return {"graph/kconfig.json": L.canon(doc)}


def main():
    files = build()
    if "--check" in sys.argv:
        bad = [k for k, v in sorted(files.items()) if not os.path.exists(os.path.join(L.X, k)) or open(os.path.join(L.X, k), "rb").read() != v]
        print(json.dumps({"check": "byte-identical" if not bad else "DIFFERENT", "bad": bad}))
        return 1 if bad else 0
    for k, v in sorted(files.items()):
        L.write_bytes(os.path.join(L.X, k), v)
    doc = json.loads(files["graph/kconfig.json"])
    print(json.dumps({"configs": len(doc["configs"]), "built_by": len(doc["built_by"]), "depends": len(doc["depends"]),
                      "selects": len(doc["selects"]), "unresolved": {k: v for k, v in doc["unresolved"].items() if k != "rows"},
                      "stats": doc["stats"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
