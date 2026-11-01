#!/usr/bin/env python3
"""lx_calls.py - BT-LXR-07: CALLS, OPS and ARCH_PAIR edges with ambig flags and unresolved counts (section 5.6).

usage: lx_calls.py [--check]     writes X/graph/calls.json
CALLS: identifier followed by `(` inside a function BODY (comments and literals blanked), matched against, in order,
the definitions of the same file, the caller's book, then lx-inc (depends_on); callable = function, function-like
macro, asm label; candidates of the other arch (arm64 vs x86) are dropped; several candidates -> all, ambig=1.
OPS: `.field = fn` inside `struct <name ending _ops|_operations> <instance> = { ... }`; edge instance -> fn.
ARCH_PAIR: same qualname (alt suffix removed) defined as a function/label under arch/arm64/ and arch/x86/.
"""
import collections, json, os, re, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lxlib as L  # noqa: E402

CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
OPS = re.compile(r"\bstruct\s+([A-Za-z0-9_]*(?:_operations|_ops))\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^\]]*\])?[^=;{()]*=\s*\{")
INIT = re.compile(r"\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*&?\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?=[,}\s])")
KEYWORDS = set("""if for while switch return sizeof typeof __typeof__ __typeof alignof _Alignof __alignof__ __attribute__
asm __asm__ volatile __volatile__ defined case do else goto __builtin_expect likely unlikely _Static_assert static_assert
__builtin_constant_p offsetof __builtin_offsetof va_arg __VA_ARGS__ _Generic __auto_type typeof_unqual""".split())
CALLABLE = {"function", "macro_fn", "asm_label"}


def base_qual(q):
    return re.sub(r"\.alt_[0-9]+$", "", q)


def load_symbols():
    """-> list of dicts (sid, path, ckind, name, qual, book, start, end) for all SYMBOL-layer records."""
    out = []
    for bk in L.BOOK_IDS:
        d = L.book_dir(bk)
        spans = {s["id"]: s["span"] for s in L.read_jsonl(os.path.join(d, "symbols.jsonl"))}
        for r in L.read_jsonl(os.path.join(d, "idmap.jsonl")):
            sp = spans[r["sid"]]
            out.append(dict(r, book=bk, start=sp["start_byte"], end=sp["end_byte"]))
    return out


def arch_ok(caller_path, callee_path):
    a, b = L.arch_tag(caller_path), L.arch_tag(callee_path)
    return a == "generic" or b == "generic" or a == b


def build():
    syms = load_symbols()
    by_file = collections.defaultdict(lambda: collections.defaultdict(list))
    by_book = collections.defaultdict(lambda: collections.defaultdict(list))
    var_by_file = collections.defaultdict(lambda: collections.defaultdict(list))
    for s in syms:
        if not s["router"]:
            continue
        top = base_qual(s["qual"])
        if "." in top:
            continue
        if s["ckind"] in CALLABLE:
            by_file[s["path"]][top].append(s)
            by_book[s["book"]][top].append(s)
        elif s["ckind"] == "variable":
            var_by_file[s["path"]][top].append(s["sid"])

    def resolve(name, caller):
        c = by_file[caller["path"]].get(name)
        if not c:
            c = by_book[caller["book"]].get(name) or by_book["lx-inc"].get(name) or []
        return sorted(x["sid"] for x in c if arch_ok(caller["path"], x["path"]))

    calls, unres, text_cache = set(), {}, {}

    def stripped(p):
        if p not in text_cache:
            text_cache.clear()
            text_cache[p] = L.strip_c(L.src_bytes(p).decode("latin-1"))
        return text_cache[p]

    for s in sorted((s for s in syms if s["ckind"] == "function" and s["router"]), key=lambda s: (s["path"], s["start"], s["sid"])):
        t = stripped(s["path"])
        body0 = t.find("{", s["start"], s["end"])
        if body0 < 0:
            continue
        n_un = 0
        for m in CALL.finditer(t, body0, s["end"]):
            nm = m.group(1)
            if nm in KEYWORDS:
                continue
            cand = resolve(nm, s)
            if not cand:
                n_un += 1
                continue
            amb = 1 if len(cand) > 1 else 0
            for c in cand:
                calls.add((s["sid"], c, amb))
        if n_un:
            unres[s["sid"]] = n_un
    ops, ops_unres = set(), 0
    files = sorted({s["path"] for s in syms if L.ext_of(s["path"]) in ("c", "h")})
    for p in files:
        t = stripped(p)
        for m in OPS.finditer(t):
            depth, i = 1, m.end()
            while i < len(t) and depth:
                depth += {"{": 1, "}": -1}.get(t[i], 0)
                i += 1
            inst = var_by_file[p].get(m.group(2))
            if not inst:
                ops_unres += 1
                continue
            caller = {"path": p, "book": L.book(p)}
            for f in INIT.finditer(t, m.end(), i):
                cand = resolve(f.group(2), caller)
                if not cand:
                    ops_unres += 1
                    continue
                for src in inst:
                    for c in cand:
                        ops.add((src, c, f.group(1), m.group(1), 1 if len(cand) > 1 else 0))
    a64, x86 = collections.defaultdict(list), collections.defaultdict(list)
    for s in syms:
        if s["router"] and s["ckind"] in ("function", "asm_label"):
            q = base_qual(s["qual"])
            if s["path"].startswith("arch/arm64/"):
                a64[q].append(s["sid"])
            elif s["path"].startswith("arch/x86/"):
                x86[q].append(s["sid"])
    pairs = []
    for q in sorted(set(a64) & set(x86)):
        amb = 1 if len(a64[q]) > 1 or len(x86[q]) > 1 else 0
        for a in sorted(a64[q]):
            for b in sorted(x86[q]):
                pairs.append([q, a, b, amb])
    doc = {"schema": "lx.calls.v1", "evidence": "DERIVED lexical", "pin": L.PIN,
           "calls_columns": ["from", "to", "ambig"], "calls": sorted(list(e) for e in calls),
           "ops_columns": ["from", "to", "field", "struct", "ambig"], "ops": sorted(list(e) for e in ops),
           "arch_pair_columns": ["qualname", "arm64", "x86", "ambig"], "arch_pair": pairs,
           "unresolved": {"calls_per_symbol": dict(sorted(unres.items())), "calls_total": sum(unres.values()), "ops_total": ops_unres}}
    return {"graph/calls.json": L.canon(doc)}


def main():
    files = build()
    if "--check" in sys.argv:
        bad = [k for k, v in sorted(files.items()) if not os.path.exists(os.path.join(L.X, k)) or open(os.path.join(L.X, k), "rb").read() != v]
        print(json.dumps({"check": "byte-identical" if not bad else "DIFFERENT", "bad": bad}))
        return 1 if bad else 0
    for k, v in sorted(files.items()):
        L.write_bytes(os.path.join(L.X, k), v)
    d = json.loads(files["graph/calls.json"])
    print(json.dumps({"calls": len(d["calls"]), "calls_ambig": sum(e[2] for e in d["calls"]), "ops": len(d["ops"]),
                      "arch_pair": len(d["arch_pair"]), "arch_pair_qualnames": len({p[0] for p in d["arch_pair"]}),
                      "unresolved_calls": d["unresolved"]["calls_total"], "symbols_with_unresolved": len(d["unresolved"]["calls_per_symbol"]),
                      "unresolved_ops": d["unresolved"]["ops_total"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
