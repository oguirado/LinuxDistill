#!/usr/bin/env python3
"""lx_query.py - host-side lx router (query classes LX-FIND, LX-WHERE, LX-IMPACT, LX-ARCHPAIR, LX-KCONFIG; section 5.8).

usage: lx_query.py [--root DIR] [--book lx-x] [--no-fresh] CLASS QUERY
  CLASS in find | where | impact | archpair | kconfig
Reads only index/ and hb/<book>/book/graph.json under --root (default X), so it runs unchanged on an unpacked shard
set. On mount every index dir's SHA256SUMS is verified (E_CHUNK_SHA) and its ID must equal the recomputed
g_lx_fresh digest (E_STALE) unless --no-fresh. Prints one canonical lx.answer.v1 JSON line and its sha256.
Budgets (kernel 8.5): answer <= 2,000 B and <= 20 rows; impact pack <= 12,288 B; fan-in > 64 -> HOT row, rc 6
E_BUDGET, never a truncated list. Abstention [TARGET-CHOSEN]: FIND on a bare identifier abstains (ABSENT) unless a
symbol in scope carries that exact name; WHERE on a path abstains unless it is a FILE node.
"""
import json, os, re, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lxlib as L  # noqa: E402

HB = L.L
ANSWER_C, ANSWER_ROWS, PACK_C, F_MAX = 2000, 20, 12288, 64
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class QErr(Exception):
    def __init__(self, code, rc, msg):
        super().__init__(f"{code}: {msg}")
        self.code, self.rc = code, rc


class Index:
    def __init__(self, d, fresh):
        self.d = d
        sums = open(os.path.join(d, "SHA256SUMS"), encoding="utf-8").read().splitlines()
        for line in sums:
            h, name = line.split("  ", 1)
            with open(os.path.join(d, name), "rb") as f:
                if L.sha256b(f.read()) != h:
                    raise QErr("E_CHUNK_SHA", 5, f"{os.path.basename(d)}/{name}")
        self.ixid = open(os.path.join(d, "ID"), encoding="utf-8").read().strip()
        if fresh is not None and self.ixid != fresh:
            raise QErr("E_STALE", 4, f"{os.path.basename(d)} index/ID {self.ixid[:12]} != g_lx_fresh {fresh[:12]}")
        self._bm = None

    def _load(self):
        d = self.d
        cols = L.jload(os.path.join(d, "cols.json"))
        self.w = cols["weights"]
        self._docs = L.jload(os.path.join(d, "docs.json"))
        post = {}
        for t, p in L.jload(os.path.join(d, "post.json")).items():
            post[t] = {f: {flat[j]: flat[j + 1] for j in range(0, len(flat), 2)} for f, flat in p["z"].items()}
        self._bm = {"N": cols["N"], "fields": cols["fields"], "lens": cols["len"], "A": cols["A"], "post": post, "cls": {}}

    @property
    def bm(self):
        if self._bm is None:
            self._load()
        return self._bm

    @property
    def docs(self):
        if self._bm is None:
            self._load()
        return self._docs

    def scores(self, terms):
        return HB.bm25f_scores(self.bm, terms, self.w)

    def exact(self, tok):
        z = self.bm["post"].get(tok, {}).get("nm", {})
        return sorted(z)


class Router:
    def __init__(self, root=L.X, fresh=True):
        self.root = root
        self.fresh = L.fresh_id() if fresh else None
        self._ix, self._g = {}, {}

    def ix(self, name):
        if name not in self._ix:
            self._ix[name] = Index(os.path.join(self.root, "index", name), self.fresh)
        return self._ix[name]

    def graph(self, bk):
        if bk not in self._g:
            self.ix(bk)                  # mount check: SHA256SUMS + index/ID freshness of the book before any read
            self._g[bk] = L.jload(os.path.join(self.root, "hb", bk, "book", "graph.json"))
        return self._g[bk]

    def answer(self, cls, q, status, rows, budget=ANSWER_C):
        ixid = self.fresh or self.ix("lx").ixid
        a = {"schema": "lx.answer.v1", "class": cls, "q": q, "index_id": ixid, "status": status, "rows": rows}
        if len(L.canon(a)) > budget:
            raise QErr("E_BUDGET", 6, f"{cls} answer exceeds {budget} B")
        return a

    def fit(self, cls, q, rows):
        """Rank cut: the longest prefix (<= 20 rows) of a RANKED list that fits the answer budget."""
        rows = rows[:ANSWER_ROWS]
        while rows and len(L.canon({"schema": "lx.answer.v1", "class": cls, "q": q, "index_id": "0" * 64, "status": "OK", "rows": rows})) > ANSWER_C:
            rows = rows[:-1]
        return rows

    def find(self, q, book=None, k=10):
        books = [book] if book else L.BOOK_IDS
        if "::" in q:
            for bk in books:
                for d in self.ix(bk).docs:
                    if d[0] == q or d[0].startswith(q + ".alt_"):
                        return self.answer("LX-FIND", q, "OK", [d[:5]])
            return self.answer("LX-FIND", q, "ABSENT", [])
        terms = HB.toks(HB.split_ident(q)) + [w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", q)]
        ident = IDENT.match(q.strip()) is not None
        cand = []
        for bk in books:
            ix = self.ix(bk)
            if ident and not ix.exact(q.strip().lower()):
                continue
            for d, s in ix.scores(terms).items():
                cand.append((-s, ix.docs[d][0], ix.docs[d][:5]))
        if not cand:
            return self.answer("LX-FIND", q, "ABSENT", [])
        cand.sort()
        return self.answer("LX-FIND", q, "OK", self.fit("LX-FIND", q, [c[2] for c in cand[:k]]))

    def where(self, q, k=8):
        ix = self.ix("lx")
        if "/" in q and "." in q.rsplit("/", 1)[-1]:
            rows = [d for d in ix.docs if d[1] == q]
            return self.answer("LX-WHERE", q, "OK" if rows else "ABSENT", rows)
        terms = HB.toks(HB.split_ident(q))
        S = ix.scores(terms)
        order = sorted(S, key=lambda d: (-S[d], ix.docs[d][1]))[:k]
        if not order:
            return self.answer("LX-WHERE", q, "ABSENT", [])
        return self.answer("LX-WHERE", q, "OK", self.fit("LX-WHERE", q, [ix.docs[d] for d in order]))

    def _book_of(self, sid):
        p = sid.split("::", 1)[0]
        return L.book(p)

    def impact(self, sid):
        callers, callees = set(), set()
        bk = self._book_of(sid)
        if bk is None:
            return self.answer("LX-IMPACT", sid, "ABSENT", [])
        for e in self.graph(bk)["edges"].get("CALLS", []):
            if e[0] == sid:
                callees.add(e[1])
        hot = {r[0]: r[1] for r in self.graph(bk)["hot"]["rows"]}
        if sid in hot:
            raise QErr("E_BUDGET", 6, json.dumps({"class": "HOT", "sid": sid, "fan_in": hot[sid]}))
        for b in L.BOOK_IDS:
            for e in self.graph(b)["edges"].get("CALLS", []):
                if e[1] == sid:
                    callers.add(e[0])
        if len(callers) > F_MAX:
            raise QErr("E_BUDGET", 6, json.dumps({"class": "HOT", "sid": sid, "fan_in": len(callers)}))
        rows = [{"sid": sid, "callers": sorted(callers), "callees": sorted(callees)}]
        return self.answer("LX-IMPACT", sid, "OK", rows, budget=PACK_C)

    def archpair(self, q):
        rows = set()
        for bk in ("lx-a64", "lx-x86", "lx-kvm"):
            for e in self.graph(bk)["edges"].get("ARCH_PAIR", []):
                if e[0] == q:
                    rows.add((e[1], e[2]))
        return self.answer("LX-ARCHPAIR", q, "OK" if rows else "ABSENT", [list(r) for r in sorted(rows)])

    def kconfig(self, q):
        built, nb = set(), set()
        for bk in L.BOOK_IDS:
            g = self.graph(bk)["edges"]
            built |= {e[0] for e in g.get("BUILT_BY", []) if e[1] == q}
            nb |= {(e[2], e[1]) for e in g.get("KCONFIG", []) if e[0] == q}
            nb |= {(e[2] + "_BY", e[0]) for e in g.get("KCONFIG", []) if e[1] == q}
        rows = [{"built_by": sorted(built)}, {"kconfig": [list(x) for x in sorted(nb)][:40]}]
        return self.answer("LX-KCONFIG", q, "OK" if built or nb else "ABSENT", rows if built or nb else [])

    def run(self, cls, q, book=None):
        try:
            if cls == "find":
                return 0, self.find(q, book)
            return 0, getattr(self, cls)(q)
        except QErr as e:
            return e.rc, {"schema": "lx.answer.v1", "class": cls, "q": q, "status": e.code, "detail": str(e)[:300]}


def answer_sha(a):
    return L.sha256b(L.canon(a))


def main():
    a = sys.argv[1:]
    root, book, fresh = L.X, None, True
    if "--root" in a:
        i = a.index("--root"); root = a[i + 1]; del a[i:i + 2]
    if "--book" in a:
        i = a.index("--book"); book = a[i + 1]; del a[i:i + 2]
    if "--no-fresh" in a:
        a.remove("--no-fresh"); fresh = False
    cls, q = a[0], a[1]
    rc, ans = Router(root, fresh).run(cls, q, book)
    sys.stdout.write(L.canon(ans).decode())
    print("answer_sha256", answer_sha(ans))
    return rc


if __name__ == "__main__":
    sys.exit(main())
