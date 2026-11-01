#!/usr/bin/env python3
"""BT-LXR-04 gate: every SYMBOL-layer file is in exactly one book manifest; 13 books; H corpus-wide; lx-inc dependency.
must-FAIL (both legs must fail): a file listed in two books; a SYMBOL-layer file in no book (synthetic fixtures)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gatelib import X, main
import lxlib as L
import lx_books as B
import lx_symbols as S


def positive():
    mans = {bk: L.jload(os.path.join(L.book_dir(bk), "manifest.json")) for bk in L.BOOK_IDS}
    ok, det = B.check_partition(S.symbol_files(), {bk: m["files"] for bk, m in mans.items()})
    Hs = {m["H"] for m in mans.values()}
    dep = all(m["depends_on"] == ([] if bk == "lx-inc" else ["lx-inc"]) for bk, m in mans.items())
    return ok and len(mans) == 13 and len(Hs) == 1 and dep, f"{det} H={sorted(Hs)} depends_on_ok={dep}"


def must_fail():
    res = []
    for f in ("file_in_two_books.json", "file_in_no_book.json"):
        fx = L.jload(os.path.join(X, "fixtures", "lx", "books", f))
        ok, det = B.check_partition(fx["symbol_files"], fx["books"])
        res.append((f, ok, det))
    return any(r[1] for r in res), "; ".join(f"{f}: {'PASS' if ok else 'FAIL'} ({d})" for f, ok, d in res)


if __name__ == "__main__":
    main(positive, must_fail)
