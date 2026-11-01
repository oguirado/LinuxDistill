#!/usr/bin/env python3
"""BT-LXR-10 gate G-LX-CONF. Positive: >= 30 rows of fixtures/lx/conf/rows.jsonl PASS against
fixtures/score_ref_lx.json with the built index at the pin. must-FAIL (every leg must fail; any passing leg = DEAD):
(a) constant-answer router; (b) stale shard: index dirs whose index/ID is not the g_lx_fresh digest (SHA256SUMS kept
consistent, so only freshness can catch it); (c) an answer carrying a ctags __anon sid."""
import json, os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gatelib import X, main
import lxlib as L
import lx_conf as CF
import lx_query as Q


def rows_ref():
    return L.read_jsonl(CF.CONF), L.jload(CF.REF)


def positive():
    rows, ref = rows_ref()
    res = CF.score(Q.Router(), rows, ref)
    n = sum(ok for _, ok, _ in res)
    return len(rows) >= 30 and n == len(rows), f"rows={len(rows)} pass={n} fail={[i for i, ok, _ in res if not ok]}"


class Constant(Q.Router):
    def run(self, cls, q, book=None):
        return Q.Router.run(self, "find", "__schedule")


class Anon(Q.Router):
    def run(self, cls, q, book=None):
        rc, a = Q.Router.run(self, cls, q, book)
        a = json.loads(L.canon(a))
        for r in a.get("rows", []):
            if isinstance(r, list) and r and isinstance(r[0], str) and "::" in r[0]:
                r[0] = r[0].split("::")[0] + "::__anon0b88a6aa0108"
                break
            if isinstance(r, dict):
                for k, v in r.items():
                    if isinstance(v, list) and v and "::" in str(v[0]):
                        v[0] = v[0].split("::")[0] + "::__anon0b88a6aa0108"
                        break
        return rc, a


def stale_root(tmp):
    os.symlink(os.path.join(X, "hb"), os.path.join(tmp, "hb"))
    old = L.fresh_id(dict(L.fresh_record(), commit="0" * 40))
    for d in ["lx"] + L.BOOK_IDS:
        src, dst = os.path.join(X, "index", d), os.path.join(tmp, "index", d)
        shutil.copytree(src, dst)
        open(os.path.join(dst, "ID"), "w").write(old + "\n")
        files = {k: open(os.path.join(dst, k), "rb").read() for k in sorted(os.listdir(dst)) if k != "SHA256SUMS"}
        open(os.path.join(dst, "SHA256SUMS"), "w").write("".join(f"{L.sha256b(v)}  {k}\n" for k, v in sorted(files.items())))
    return tmp


def must_fail():
    rows, ref = rows_ref()
    out = []
    for name, router in (("constant", Constant()), ("anon", Anon())):
        res = CF.score(router, rows, None)          # gold predicate only: the ref answers cannot rescue a leg
        out.append((name, all(ok for _, ok, _ in res), sum(ok for _, ok, _ in res)))
    with tempfile.TemporaryDirectory(prefix="lx_stale_", dir=os.environ.get("LX_TMP")) as tmp:
        res = CF.score(Q.Router(stale_root(tmp)), rows, None)
        out.append(("stale", all(ok for _, ok, _ in res), sum(ok for _, ok, _ in res)))
    return any(o[1] for o in out), "; ".join(f"{n}: {'PASS' if a else 'FAIL'} ({p}/{len(rows)} rows)" for n, a, p in out)


if __name__ == "__main__":
    main(positive, must_fail)
