#!/usr/bin/env python3
"""Shared helpers for hbtools_v2: canonical JSON, hashes, tokeniser, UTF-8 byte law, integer BM25F pieces.

Stdlib only, no floats in any artefact. Every serialised artefact is sorted-keys, compact separators, LF.
"""
import hashlib, importlib.util, json, os, sys
from decimal import Decimal

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
HB = os.path.dirname(HERE)
SUBJECT = os.path.join(HB, "subject")
M64 = (1 << 64) - 1
ANSWER_C, ANSWER_H = 2000, 200
PACK_C, PACK_H = 12288, 256
SYM_MAX = 1800          # D-HB2-11: symbol <= 1,800 B -> one anchor
SKEL_MAX = 800


def dumps(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canon(o):
    """Canonical artefact bytes: sorted keys, compact, LF terminated, UTF-8."""
    return (dumps(o) + "\n").encode("utf-8")


def write_json(path, o):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "wb") as f:
        f.write(canon(o))


def write_jsonl(path, rows):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "wb") as f:
        for r in rows:
            f.write(canon(r))


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def readb(path):
    with open(path, "rb") as f:
        return f.read()


def sha256b(b):
    return hashlib.sha256(b).hexdigest()


def sha256s(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha16(b):
    return hashlib.sha256(b).hexdigest()[:16]


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


def fnv1a64(b):
    h = 0xcbf29ce484222325
    for x in b:
        h = ((h ^ x) * 0x100000001b3) & M64
    return h


def fnv16(b):
    return "%016x" % fnv1a64(b)


EMPTY_SHA256 = sha256b(b"")


def blen(s):
    """UTF-8 byte length (the byte law: every budget counts bytes, tokens are reported only)."""
    return len(s.encode("utf-8"))


def clip_bytes(s, n):
    """Longest prefix of s with UTF-8 length <= n, cut on a code-point boundary."""
    b = s.encode("utf-8")
    return s if len(b) <= n else b[:n].decode("utf-8", "ignore")


def ser_len(o):
    """UTF-8 length of the exact serialisation + LF (the budget measure of D-HB2-11)."""
    return len(canon(o))


def clean_pycache(root):
    """Remove __pycache__ dirs that subprocess tests may have created inside a frozen tree."""
    import shutil
    for dp, dn, fn in os.walk(root):
        for d in list(dn):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dp, d), ignore_errors=True)
                dn.remove(d)


def tree_files(root, exts=None, skip=("__pycache__", ".git")):
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = sorted(d for d in dn if d not in skip)
        for f in sorted(fn):
            if exts is None or os.path.splitext(f)[1] in exts:
                out.append(os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/"))
    return sorted(out)


# ---- router v2 reuse -------------------------------------------------------------------------------
_RV2 = {}


def load_mod(subject, relpath, name=None):
    """Import a subject tool module by file path without leaving bytecode in the frozen tree."""
    key = (os.path.abspath(subject), relpath)
    if key in _RV2:
        return _RV2[key]
    p = os.path.join(subject, relpath)
    spec = importlib.util.spec_from_file_location(name or ("subj_" + os.path.splitext(os.path.basename(relpath))[0]), p)
    m = importlib.util.module_from_spec(spec)
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    spec.loader.exec_module(m)
    sys.dont_write_bytecode = old
    _RV2[key] = m
    return m


def router(subject=SUBJECT):
    return load_mod(subject, "tools/route_v2.py")


def toks(text, subject=SUBJECT):
    """The router v2 tokeniser (route_v2.toks): NFKC, casefold, latex words, [0-9a-z]+, len > 1, stop words."""
    return router(subject).toks(text)


def split_ident(name):
    """Identifier text -> words (snake and camel); used so symbol names tokenise like prose."""
    out, cur = [], ""
    for i, ch in enumerate(name):
        if ch == "_" or ch == "." or ch == "/" or ch == "-":
            if cur:
                out.append(cur)
            cur = ""
            continue
        if ch.isupper() and cur and (cur[-1].islower() or (i + 1 < len(name) and name[i + 1].islower() and cur[-1].isupper())):
            out.append(cur)
            cur = ""
        cur += ch
    if cur:
        out.append(cur)
    return " ".join(out)


def lcp5(t):
    return t[:5] if len(t) >= 5 else t


# ---- integer BM25F (router v2 formulas) -------------------------------------------------------------
K_BM = 1200000
B_PPM = 750000


def idf_ppm(N, df):
    """Router v2 idf in ppm: floor(1e6 * ln(1 + (N - df + .5) / (df + .5))), df >= 1 (Decimal, no float)."""
    df = max(df, 1)
    v = (Decimal(1) + (Decimal(N - df) + Decimal("0.5")) / (Decimal(df) + Decimal("0.5"))).ln()
    return int((v * 1000000).to_integral_value(rounding="ROUND_FLOOR"))


def zone_x(A, B, ln, tf, w_f):
    """Per-field saturating input (route_v2.zone_x): w*tf*1e9 // (1e6 - B + B*ratio/1e6)."""
    ratio = (ln * 10 ** 9) // A if A else 10 ** 6
    norm = (10 ** 6 - B) + (B * ratio) // 10 ** 6
    return (w_f * tf * 10 ** 9) // norm


def term_score(idf, acc):
    return (idf * acc) // (K_BM + acc)


def is_float_free(o):
    if isinstance(o, float):
        return False
    if isinstance(o, dict):
        return all(is_float_free(v) for v in o.values())
    if isinstance(o, (list, tuple)):
        return all(is_float_free(v) for v in o)
    return True


# ---- exact decimal formatting (no floats in artefacts) ----------------------------------------------
def fmt_dec(fr, places=3):
    """Fraction -> decimal string rounded half-up to `places` digits ('0.529')."""
    from fractions import Fraction
    fr = Fraction(fr)
    scale = 10 ** places
    n = (abs(fr.numerator) * scale * 2 + fr.denominator) // (2 * fr.denominator)
    s = ("%d.%0*d" % (n // scale, places, n % scale)) if places > 0 else "%d" % n
    return ("-" + s) if fr < 0 else s


def median_up(vals):
    v = sorted(vals)
    return v[len(v) // 2] if v else 0


def pctl(vals, p):
    """Nearest-rank percentile (integer p in 1..100) of a list of ints."""
    v = sorted(vals)
    if not v:
        return 0
    k = max(1, -(-p * len(v) // 100))
    return v[k - 1]


# ---- generic integer BM25F over token fields (router v2 code path, ppm arithmetic) -------------------
def bm25f_index(docs, fields):
    """docs: list of {field: [tokens]}; returns an index dict with A_f, per-term postings and lcp5 classes."""
    N = len(docs)
    lens = {f: [len(d.get(f, ())) for d in docs] for f in fields}
    A = {f: (1000 * sum(lens[f])) // N if N else 0 for f in fields}
    post = {}
    for i, d in enumerate(docs):
        for f in fields:
            for t in d.get(f, ()):
                post.setdefault(t, {}).setdefault(f, {})
                post[t][f][i] = post[t][f].get(i, 0) + 1
    cls = {}
    for t in sorted(post):
        if len(t) >= 5:
            cls.setdefault(t[:5], []).append(t)
    return dict(N=N, fields=list(fields), lens=lens, A=A, post=post, cls=cls)


def bm25f_vposting(ix, t, lcp):
    """-> (idf_ppm, df, {field: {doc: tf}}) following route_v2.vposting."""
    N = ix["N"]
    idf1 = idf_ppm(N, 1)
    if lcp and len(t) >= 5:
        ts = ix["cls"].get(t[:5])
        if not ts:
            return idf1, 0, {}
        z, docs = {}, set()
        for ct in ts:
            for f, dm in ix["post"][ct].items():
                zz = z.setdefault(f, {})
                for d, tf in dm.items():
                    zz[d] = zz.get(d, 0) + tf
                    docs.add(d)
        return idf_ppm(N, len(docs)), len(docs), z
    p = ix["post"].get(t)
    if not p:
        return idf1, 0, {}
    docs = set()
    for dm in p.values():
        docs |= set(dm)
    return idf_ppm(N, len(docs)), len(docs), p


def bm25f_scores(ix, qterms, weights, lcp=False, b_ppm=B_PPM):
    """Integer score per doc index: sum over distinct query terms of idf*acc // (K + acc)."""
    S = {}
    for t in sorted(set(qterms)):
        idf, df, z = bm25f_vposting(ix, t, lcp)
        acc = {}
        for f, wf in weights.items():
            if not wf or f not in z:
                continue
            for d, tf in z[f].items():
                acc[d] = acc.get(d, 0) + zone_x(ix["A"][f], b_ppm, ix["lens"][f][d], tf, wf)
        for d, a in acc.items():
            S[d] = S.get(d, 0) + (idf * a) // (K_BM + a)
    return {d: v for d, v in S.items() if v > 0}


def rank_order(S, keys):
    """Order doc indices by (-S, natural key); keys[i] is the natural id of doc i."""
    return sorted(S, key=lambda d: (-S[d], keys[d]))
