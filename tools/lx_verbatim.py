#!/usr/bin/env python3
"""lx_verbatim.py - measure verbatim overlap between the study outputs and the Linux snapshot.
Token 10-grams of the snapshot go in a set of hashes; each string value in a study file is scanned for its longest
run of consecutive tokens found in the snapshot. usage: lx_verbatim.py [repository root]"""
import glob, hashlib, json, os, re, sys, collections
ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
SRC = os.path.join(ROOT, "rcu-free-v3@5495317", "src")
N = 10
TOK = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[^\sA-Za-z0-9_]")
h = lambda t: hash(t)
grams = set()
for d, _, fs in os.walk(SRC):
    for f in fs:
        p = os.path.join(d, f)
        if os.path.islink(p): continue
        try:
            b = open(p, "rb").read()
        except OSError:
            continue
        t = TOK.findall(b.decode("latin1"))
        for i in range(len(t) - N + 1):
            grams.add(h(tuple(t[i:i + N])))
print("grams", len(grams), flush=True)


def strings(o):
    if isinstance(o, str): yield o
    elif isinstance(o, dict):
        for v in o.values(): yield from strings(v)
    elif isinstance(o, list):
        for v in o: yield from strings(v)


hist = collections.Counter(); tops = []; files = 0; strs = 0; total_tokens = 0; copied = 0
for lvl in ("extracts", "partials", "dossiers", "review"):
    for p in glob.glob(os.path.join(ROOT, "study", "pass1", lvl, "*.json")):
        files += 1
        try:
            o = json.load(open(p))
        except Exception:
            continue
        for s in strings(o):
            t = TOK.findall(s); strs += 1; total_tokens += len(t)
            i = 0; best = 0; bi = 0
            while i <= len(t) - N:
                if h(tuple(t[i:i + N])) in grams:
                    j = i + 1
                    while j <= len(t) - N and h(tuple(t[j:j + N])) in grams: j += 1
                    L = j - i + N - 1
                    copied += L
                    if L > best: best, bi = L, i
                    i = j + N - 1
                else:
                    i += 1
            if best:
                b = "10-14" if best < 15 else "15-24" if best < 25 else "25-49" if best < 50 else "50+"
                hist[b] += 1
                tops.append((best, os.path.relpath(p, ROOT), " ".join(t[bi:bi + best])[:220]))
tops.sort(key=lambda x: -x[0])
print(json.dumps({"files": files, "strings": strs, "tokens": total_tokens, "tokens_in_runs": copied, "strings_by_longest_run": hist}, indent=0))
for x in tops[:25]: print(x)
