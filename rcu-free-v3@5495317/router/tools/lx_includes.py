#!/usr/bin/env python3
"""lx_includes.py - BT-LXR-05: INCLUDES edges computed twice (arm64, x86) and the ROUTE closure (CL-1..CL-5).

usage: lx_includes.py [--check]
Resolution order (section 5.6): quote-relative, include/, include/uapi, arch/<a>/include, arch/<a>/include/uapi,
generated -> ABSENT leaf; <asm/X.h> -> arch header, else generated-y -> ABSENT, else asm-generic when X.h is in
generic-y (arch Kbuild) or mandatory-y (asm-generic Kbuild). Every #if branch counts (lexical over-approximation);
commented-out includes are ignored. Roots: T0-S and T1-F code files (arch/<other>/ excluded per arch).
Writes X/graph/includes.json and X/closure/{route_closure.txt,CLOSURE.arm64.tsv,CLOSURE.x86.tsv,closure_cut.tsv,report.json}.
"""
import json, os, posixpath, re, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lxlib as L  # noqa: E402

INC = re.compile(r'^[ \t]*#[ \t]*include[ \t]*([<"])([^>"\n]+)[>"]', re.M)
ARCHES = ("arm64", "x86")
BUDGET_B = 60_000_000          # CL-5: ROUTE-SYMBOL <= 60 MB  [TARGET]
BUDGET_TOK = 20_000_000        # and <= 20 Mtok at 3.2 B/tok  [TARGET]
DEPTH_MAX = 6


def kbuild_names(path, keys):
    if path not in L.manifest():
        return set()
    t = L.src_bytes(path).decode("latin-1").replace("\\\n", " ")
    out = set()
    for m in re.finditer(r"^[ \t]*(" + "|".join(keys) + r")[ \t]*[+:]?=[ \t]*(.*)$", t, re.M):
        out |= {w for w in m.group(2).split() if w.endswith(".h")}
    return out


def includes_of(p):
    raw = L.src_bytes(p).decode("latin-1")
    mask = L.strip_c(raw)
    out = []
    for m in INC.finditer(raw):
        h = raw.find("#", m.start())
        if mask[h] == "#":
            out.append((m.group(1), m.group(2).strip()))
    return out


class Resolver:
    def __init__(self, arch):
        pool = L.manifest()
        self.pool, self.a = pool, arch
        ai = f"arch/{arch}/include"
        self.gen = kbuild_names(f"{ai}/asm/Kbuild", ["generic-y", "mandatory-y"]) | kbuild_names("include/asm-generic/Kbuild", ["mandatory-y"])
        self.ugen = kbuild_names(f"{ai}/uapi/asm/Kbuild", ["generic-y", "mandatory-y"]) | kbuild_names("include/uapi/asm-generic/Kbuild", ["mandatory-y"])
        self.generated = kbuild_names(f"{ai}/asm/Kbuild", ["generated-y"]) | kbuild_names(f"{ai}/uapi/asm/Kbuild", ["generated-y"])

    def resolve(self, q, inc, src):
        """-> (target path or None, reason)."""
        a, pool = self.a, self.pool
        if inc.startswith("generated/") or "/generated/" in inc:
            return None, "generated"
        if q == '"':
            c = posixpath.normpath(posixpath.join(posixpath.dirname(src), inc))
            if not c.startswith("../") and c in pool:
                return c, "quote"
        if inc.startswith("asm/"):
            x = inc[4:]
            for c in (f"arch/{a}/include/asm/{x}", f"arch/{a}/include/uapi/asm/{x}"):
                if c in pool:
                    return c, "arch"
            if x in self.generated:
                return None, "generated"
            if x in self.gen or x in self.ugen:
                for c in (f"include/asm-generic/{x}", f"include/uapi/asm-generic/{x}"):
                    if c in pool:
                        return c, "asm-generic"
            return None, "missing"
        for c in (f"include/{inc}", f"include/uapi/{inc}", f"arch/{a}/include/{inc}", f"arch/{a}/include/uapi/{inc}"):
            if c in pool:
                return c, "path"
        return None, "outside_pool"


def roots(arch, tiers):
    other = [f"arch/{x}/" for x in ARCHES if x != arch]
    return sorted(p for p, r in L.manifest().items() if r["tier"] in tiers and L.is_code(p)
                  and not any(p.startswith(o) for o in other))


def walk(arch, root_list, cache):
    rs = Resolver(arch)
    depth, edges, queue, i = {}, {}, [], 0
    for r in root_list:
        depth[r] = 0
        queue.append(r)
    while i < len(queue):                       # BFS: depth = shortest include distance from a root
        p = queue[i]
        i += 1
        if p not in cache:
            cache[p] = includes_of(p)
        for q, inc in cache[p]:
            tgt, why = rs.resolve(q, inc, p)
            edges[(p, inc)] = (tgt, why)
            if tgt is not None and tgt not in depth:
                depth[tgt] = depth[p] + 1
                queue.append(tgt)
    return depth, edges


def build():
    man = L.manifest()
    cache, per = {}, {}
    for a in ARCHES:
        d_all, e_all = walk(a, roots(a, ("T0-S", "T1-F")), cache)
        d_t0, _ = walk(a, roots(a, ("T0-S",)), cache)
        per[a] = (d_all, e_all, d_t0)
    # union of edges with arch tags (CL-4)
    keys = sorted(set(per["arm64"][1]) | set(per["x86"][1]))
    edges, absent, total = [], {"generated": 0, "missing": 0, "outside_pool": 0}, 0
    for k in keys:
        ra, rx = per["arm64"][1].get(k), per["x86"][1].get(k)
        if ra is not None and ra == rx:
            res = [(ra, "both")]
        else:
            res = [(r, a) for r, a in ((ra, "arm64"), (rx, "x86")) if r is not None]
        for (tgt, why), tag in res:
            edges.append([k[0], k[1], tgt, tag, why])
            total += 1
            if tgt is None:
                absent[why] += 1
    # closure = T0-I headers reached (CL-4 union, tags, min depth, T0-only flag)
    clo = {}
    for a in ARCHES:
        d_all, _, d_t0 = per[a]
        for p, d in d_all.items():
            if man[p]["tier"] != "T0-I" or not p.endswith(".h"):
                continue
            c = clo.setdefault(p, {"tags": set(), "depth": d, "t0": False})
            c["tags"].add(a)
            c["depth"] = min(c["depth"], d)
            c["t0"] = c["t0"] or p in d_t0
    t0s_bytes = sum(r["bytes"] for r in man.values() if r["tier"] == "T0-S")
    keep = sorted(clo)
    size = lambda ks: t0s_bytes + sum(man[p]["bytes"] for p in ks)  # noqa: E731
    over = lambda ks: size(ks) > BUDGET_B or size(ks) * 10 // 32 > BUDGET_TOK  # noqa: E731
    cut = []
    for reason, pred, order in (("t1_only", lambda p: not clo[p]["t0"], lambda p: p),
                                (f"depth>{DEPTH_MAX}", lambda p: clo[p]["depth"] > DEPTH_MAX, lambda p: (-clo[p]["depth"], p))):
        for p in sorted([p for p in keep if pred(p)], key=order):
            if not over(keep):
                break
            keep.remove(p)
            cut.append([p, reason])
    kset = set(keep)
    tag = lambda p: "both" if len(clo[p]["tags"]) == 2 else sorted(clo[p]["tags"])[0]  # noqa: E731
    files = {}
    files["graph/includes.json"] = L.canon({"schema": "lx.includes.v1", "evidence": "DERIVED lexical", "pin": L.PIN,
                                           "columns": ["from", "inc", "to", "arch", "how"], "edges": edges})
    files["closure/route_closure.txt"] = "".join(p + "\n" for p in keep).encode()
    for a in ARCHES:
        rows = ["path\tdepth\ttag\treach\tkept\n"] + [f"{p}\t{clo[p]['depth']}\t{tag(p)}\t{'T0' if clo[p]['t0'] else 'T1-only'}\t{int(p in kset)}\n"
                                                     for p in sorted(clo) if a in clo[p]["tags"]]
        files[f"closure/CLOSURE.{a}.tsv"] = "".join(rows).encode()
    files["closure/closure_cut.tsv"] = ("path\treason\n" + "".join(f"{p}\t{r}\n" for p, r in cut)).encode()
    n_abs = sum(absent.values())
    rep = {"schema": "lx.closure.report.v1", "roots_T0S_T1F": {a: len(roots(a, ("T0-S", "T1-F"))) for a in ARCHES},
           "closure_headers_reached": len(clo), "closure_kept_files": len(keep), "closure_cut": len(cut),
           "closure_kept_bytes": sum(man[p]["bytes"] for p in keep), "t0s_bytes": t0s_bytes,
           "route_symbol_bytes": size(keep), "route_symbol_tok_at_3_2": size(keep) * 10 // 32,
           "budget_bytes": BUDGET_B, "budget_tok": BUDGET_TOK,
           "include_edges": total, "absent_edges": absent, "absent_share_ppm": (10 ** 6 * n_abs) // max(1, total),
           "od_lx_prepare_trigger_5pct": n_abs * 20 > total,
           "tags": {t: sum(1 for p in keep if tag(p) == t) for t in ("arm64", "x86", "both")}}
    files["closure/report.json"] = L.canon(rep)
    return files


def main():
    files = build()
    if "--check" in sys.argv:
        bad = [k for k, v in sorted(files.items()) if not os.path.exists(os.path.join(L.X, k)) or open(os.path.join(L.X, k), "rb").read() != v]
        print(json.dumps({"check": "byte-identical" if not bad else "DIFFERENT", "bad": bad}))
        return 1 if bad else 0
    for k, v in sorted(files.items()):
        L.write_bytes(os.path.join(L.X, k), v)
    rep = json.loads(files["closure/report.json"])
    print(json.dumps(rep, sort_keys=True))
    print(f"closure: {rep['closure_kept_files']} files, {rep['closure_kept_bytes'] / 1e6:.2f} MB; ROUTE-SYMBOL {rep['route_symbol_bytes'] / 1e6:.2f} MB; "
          f"ABSENT include edges {rep['absent_share_ppm'] / 1e4:.2f} %")
    return 0


if __name__ == "__main__":
    sys.exit(main())
