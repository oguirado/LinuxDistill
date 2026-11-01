"""xcheck.py - mechanical ground truth independent of the ctags/lexer pipeline: GNU grep (/usr/bin/grep, LC_ALL=C)
over src/. Used by the BT-LXR-07 gate and by the G-LX-CONF generator. Only paths, line numbers, sids and identifiers
are produced; no source text leaves this module."""
import collections, os, re, subprocess, sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import lxlib as L  # noqa: E402
import lx_calls as C  # noqa: E402

GREP = "/usr/bin/grep"
COMMENT_LED = re.compile(r"^\s*(/\*|//|\*(\s|/|$))")


def grep(args):
    p = subprocess.run([GREP] + args, cwd=L.SRC, env=L.ENV, capture_output=True)
    return p.stdout.decode("latin-1").splitlines()


def grep_files(name, globs=("*.c", "*.h", "*.S")):
    inc = [f"--include={g}" for g in globs]
    return sorted(l[2:] if l.startswith("./") else l for l in grep(["-rlw"] + inc + ["--", name, "."]))


def grep_callers(sym, funcs_in_file):
    """Caller sids of `sym` from `grep -nw name file`: lines where the name is followed by '(' (definition line and
    comment-led lines excluded: /*, //, or a lone '*' continuation), mapped to the enclosing function span by line numbers. Returns None if a call line is outside any
    function (then the case is not a clean cross-check)."""
    name, path = sym["name"], sym["path"]
    pat = re.compile(r"\b" + re.escape(name) + r"\s*\(")
    out = set()
    for l in grep(["-nw", "--", name, path]):
        n, txt = l.split(":", 1)
        n = int(n)
        if n == sym["line"] or not pat.search(txt) or COMMENT_LED.match(txt):
            continue
        enc = [f for f in funcs_in_file if f["l1"] <= n <= f["l2"] and f["sid"] != sym["sid"]]
        if not enc:
            return None
        out |= {f["sid"] for f in enc}
    return out


def callers_from_graph(calls_doc):
    rev = collections.defaultdict(set)
    for a, b, _ in calls_doc["calls"]:
        rev[b].add(a)
    return rev


def pick_static(syms, books, per_book=1, max_scan=400):
    """Deterministic pick (sid order) of file-static, uniquely named functions with >= 1 grep caller, per book."""
    tops = collections.Counter(C.base_qual(s["qual"]) for s in syms if s["router"])
    by_file = collections.defaultdict(list)
    for s in syms:
        if s["ckind"] == "function":
            by_file[s["path"]].append(dict(s, l1=s["line"], l2=s["line"] + L.src_bytes(s["path"])[s["start"]:s["end"]].count(b"\n") - 1))
    picks = []
    for bk in books:
        got, scanned = 0, 0
        for s in sorted((s for s in syms if s["book"] == bk and s["ckind"] == "function" and s["router"] and s["alt"] == 0
                         and "." not in s["qual"] and s["path"].endswith(".c") and tops[s["qual"]] == 1), key=lambda s: s["sid"]):
            if got >= per_book or scanned >= max_scan:
                break
            b = L.src_bytes(s["path"])
            if not b[s["start"]:s["start"] + 7] == b"static ":
                continue
            scanned += 1
            if grep_files(s["name"]) != [s["path"]]:
                continue
            gold = grep_callers(s, by_file[s["path"]])
            if not gold or len(gold) > 64:
                continue
            picks.append((s, sorted(gold)))
            got += 1
    return picks
