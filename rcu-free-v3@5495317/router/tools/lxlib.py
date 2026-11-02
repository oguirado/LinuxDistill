#!/usr/bin/env python3
"""lxlib.py - shared helpers of the lx router tools (LINUX_DISTILL_STRATEGY_v1 section 5).

Stdlib only. Reuses the vendored HB2 engine read-only (hblib2: canonical JSON, integer BM25F, tokeniser;
schemalib: hb.*.v2 validation). Every artefact is canonical JSON (sorted keys, compact, LF), every list is
sorted, so two runs with a different cwd, TZ or PYTHONHASHSEED write identical bytes.
Clean room: records hold paths, sids, byte spans, hashes and short identifiers only, never Linux text.
"""
import hashlib, json, os, re, subprocess, sys

sys.dont_write_bytecode = True
TOOLS = os.path.dirname(os.path.abspath(__file__))
X = os.path.dirname(TOOLS)                       # D/router
D = os.path.dirname(X)                           # D = R/rcu-free-v3@5495317
R = os.path.dirname(D)                           # R = repository root
SRC = os.path.join(D, "src")
META = os.path.join(D, "meta")
HBTOOLS = os.path.join(X, "vendor", "hb", "tools")
sys.path.insert(0, HBTOOLS)
import hblib2 as L          # noqa: E402  (engine, read-only)
import schemalib as SL      # noqa: E402

PIN = "549531755d329ec48439e3263535351ba1c5acd5"
TREE = "e56d24e86147e65a8ade3cfe69dee2bfdac279fa"
PACKAGE = "lx-5495317-v1"
CORPUS = "lx"
IDMAX = 32 - len(CORPUS) - 1                     # 29 (D width law)
CTAGS = "/usr/bin/ctags"
MACROS = os.path.join(TOOLS, "lx_macros.ctags")
MV_ROUTER = os.path.join(X, "vendor", "mv")
SID_RE = re.compile(r"^[A-Za-z0-9_./-]{1,160}::[A-Za-z_][A-Za-z0-9_.]{0,127}(#b[0-9]{1,3})?$")
ENV = {"LC_ALL": "C", "TZ": "UTC", "PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}

dumps, canon = L.dumps, L.canon
sha256b = L.sha256b


def write_bytes(path, b):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(b)
    os.replace(tmp, path)


def write_json(path, o):
    write_bytes(path, canon(o))


def jsonl_bytes(rows):
    return b"".join(canon(r) for r in rows)


def write_jsonl(path, rows):
    write_bytes(path, jsonl_bytes(rows))


def read_jsonl(path):
    return L.read_jsonl(path)


def jload(path):
    return L.jload(path)


def sha_file(path):
    return L.sha_file(path)


def rel(path):
    """Path relative to R (never an absolute /home path inside an artefact)."""
    return os.path.relpath(path, R).replace(os.sep, "/")


# ---- corpus ---------------------------------------------------------------------------------------------
_MAN = None


def manifest():
    """MANIFEST.jsonl rows keyed by path (read-only input of BT-LX-01)."""
    global _MAN
    if _MAN is None:
        _MAN = {}
        with open(os.path.join(META, "MANIFEST.jsonl"), encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                _MAN[r["path"]] = r
    return _MAN


def src_bytes(path):
    with open(os.path.join(SRC, path), "rb") as f:
        return f.read()


def ext_of(p):
    b = p.rsplit("/", 1)[-1]
    return b.rsplit(".", 1)[-1] if "." in b else ""


T1F_DOC = ("Documentation/RCU/", "Documentation/locking/", "Documentation/scheduler/", "Documentation/mm/",
           "Documentation/virt/", "Documentation/core-api/", "Documentation/arch/arm64/", "Documentation/arch/x86/")


def keep_lx(p):
    """KEEP_LX (section 5.1 rule 4): .c .h .S, Kconfig*, Makefile, Kbuild, .rst under the T1-F Documentation subtrees."""
    b = p.rsplit("/", 1)[-1]
    if ext_of(p) in ("c", "h", "S"):
        return True
    if b.startswith("Kconfig") or b in ("Makefile", "Kbuild"):
        return True
    return p.endswith(".rst") and p.startswith(T1F_DOC)


def is_code(p):
    return ext_of(p) in ("c", "h", "S")


# ---- books (section 5.2, longest prefix) -----------------------------------------------------------------
BOOKS = [
    ("kernel/sched/", "lx-sched"), ("kernel/rcu/", "lx-rcu"), ("kernel/locking/", "lx-locking"),
    ("kernel/futex/", "lx-locking"), ("kernel/time/", "lx-time"), ("kernel/irq/", "lx-irq"),
    ("kernel/", "lx-kcore"), ("ipc/", "lx-kcore"), ("lib/", "lx-kcore"),
    ("mm/", "lx-mm"), ("virt/", "lx-kvm"), ("arch/arm64/kvm/", "lx-kvm"), ("arch/x86/kvm/", "lx-kvm"),
    ("arch/arm64/", "lx-a64"), ("arch/x86/", "lx-x86"),
    ("drivers/virtio/", "lx-dev"), ("drivers/block/virtio_blk.c", "lx-dev"),
    ("drivers/char/virtio_console.c", "lx-dev"), ("drivers/net/virtio_net.c", "lx-dev"),
    ("drivers/irqchip/", "lx-dev"), ("drivers/clocksource/", "lx-dev"), ("drivers/tty/", "lx-dev"),
    ("init/", "lx-boot"), ("fs/", "lx-boot"),
    ("include/", "lx-inc"),
]
BOOK_IDS = sorted({b for _, b in BOOKS})
assert len(BOOK_IDS) == 13


def book(path):
    hits = [(len(p), b) for p, b in BOOKS if path == p or (p.endswith("/") and path.startswith(p))]
    return max(hits)[1] if hits else None


def book_dir(b):
    return os.path.join(X, "hb", b, "book")


# ---- phase map (BT-SEL-3 draft, spec/PHASEMAP.tsv) -------------------------------------------------------
_PM = None


def phasemap():
    global _PM
    if _PM is None:
        _PM = []
        with open(os.path.join(R, "spec", "PHASEMAP.tsv"), encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i == 0 or not line.strip():
                    continue
                pre, ph, crown = line.rstrip("\n").split("\t")[:3]
                _PM.append((pre, ph.split(","), crown))
    return _PM


def phases(path):
    best = None
    for pre, ph, _ in phasemap():
        if path == pre or (pre.endswith("/") and path.startswith(pre)):
            if best is None or len(pre) > len(best[0]):
                best = (pre, ph)
    return best[1] if best else []


def arch_tag(path):
    if path.startswith("arch/arm64/"):
        return "arm64"
    if path.startswith("arch/x86/"):
        return "x86"
    return "generic"


# ---- sid and node id rules (sections 5.4, 5.5) ------------------------------------------------------------
def esc_path(p):
    return re.sub(r"[^A-Za-z0-9_./-]", "_", p)


def node_id(sid, H):
    path, qual = sid.split("::", 1)
    stem = path.rsplit("/", 1)[-1].split(".", 1)[0]
    pre = (stem + "." + qual).replace("#", "_")
    return pre[:IDMAX - 1 - H] + "_" + hashlib.sha256(sid.encode()).hexdigest()[:H]


class LxError(Exception):
    def __init__(self, code, msg):
        super().__init__(f"{code}: {msg}")
        self.code = code


# ---- C lexical helpers -----------------------------------------------------------------------------------
def strip_c(text):
    """Blank comments and string/char literals with spaces (newlines kept): same length, same byte offsets.
    `text` is latin-1 decoded file bytes, so index == byte offset."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif c == '"' or c == "'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            for k in range(i + 1, j - 1):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


def line_starts(b):
    st = [0]
    i = b.find(b"\n")
    while i >= 0:
        st.append(i + 1)
        i = b.find(b"\n", i + 1)
    return st


def span_of_lines(starts, size, l1, l2):
    """Byte span [start, end) of lines l1..l2 (1-based, inclusive)."""
    l2 = max(l1, min(l2, len(starts)))
    s = starts[l1 - 1]
    e = starts[l2] if l2 < len(starts) else size
    return s, e


def lex_sha(b):
    """sha256 of the lexical token stream (comments blanked, whitespace collapsed): the C stand-in for sha256_ast."""
    t = strip_c(b.decode("latin-1"))
    return sha256b(" ".join(t.split()).encode("latin-1"))


# ---- ctags ---------------------------------------------------------------------------------------------
CTAGS_BASE = [CTAGS, "--options=NONE", "--output-format=json", "--fields=+neSzp", "--fields=-T",
              "--languages=C", "--langmap=C:+.h", "--kinds-C=fsugtvdem", "--sort=no"]


def run_ctags(paths, macros=MACROS, cwd=SRC):
    """Universal Ctags over `paths` (relative to cwd); returns the parsed tag dicts sorted (path, line, name, kind)."""
    argv = list(CTAGS_BASE)
    if macros:
        argv.append("--options=" + macros)
    argv += ["-o", "-", "-L", "-"]
    p = subprocess.run(argv, input=("\n".join(paths) + "\n").encode(), cwd=cwd, env=ENV,
                       capture_output=True, check=False)
    if p.returncode != 0:
        raise LxError("E_CTAGS", p.stderr.decode("utf-8", "replace")[:300])
    tags = []
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        if not line.startswith("{"):
            continue
        t = json.loads(line)
        if t.get("_type") == "tag":
            t.pop("pattern", None)
            t["_i"] = len(tags)          # ctags emission order = parse (byte) order inside a file
            tags.append(t)
    tags.sort(key=lambda t: (t["path"], t.get("line", 0), t["_i"]))
    return tags


# ---- asm labels (LX-SID-d) -------------------------------------------------------------------------------
ASM_START = re.compile(r"^[ \t]*(SYM_FUNC_START|SYM_FUNC_START_LOCAL|SYM_FUNC_START_WEAK|SYM_FUNC_START_NOALIGN|"
                       r"SYM_FUNC_START_LOCAL_NOALIGN|SYM_TYPED_FUNC_START|SYM_CODE_START|SYM_CODE_START_LOCAL|"
                       r"SYM_CODE_START_NOALIGN|SYM_CODE_START_LOCAL_NOALIGN|ENTRY)\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", re.M)
ASM_END = re.compile(r"^[ \t]*(SYM_FUNC_END|SYM_CODE_END|END|ENDPROC|SYM_FUNC_END_ALIAS)\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", re.M)


def asm_labels(b):
    """-> [(name, start_line, end_line)] in byte order; span to the matching *_END(label) or the next label."""
    t = b.decode("latin-1")
    starts = [(m.start(), m.group(2)) for m in ASM_START.finditer(t)]
    ends = {}
    for m in ASM_END.finditer(t):
        ends.setdefault(m.group(2), []).append(m.start())
    out = []
    for i, (off, name) in enumerate(starts):
        nxt = starts[i + 1][0] if i + 1 < len(starts) else len(t)
        e = [x for x in ends.get(name, []) if x > off]
        end_off = e[0] if e else max(off, nxt - 1)
        out.append((name, t.count("\n", 0, off) + 1, t.count("\n", 0, end_off) + 1))
    return out


def tool_digest(names):
    """sha256 over sorted (name, sha256(file)) of builder tools: one value for the freshness record."""
    rows = [f"{n} {sha_file(os.path.join(TOOLS, n))}" for n in sorted(names)]
    return sha256b(("\n".join(rows) + "\n").encode())


BUILDER_TOOLS = ["lxlib.py", "lx_symbols.py", "lx_books.py", "lx_includes.py", "lx_kbuild.py", "lx_calls.py",
                 "lx_graph.py", "lx_index.py"]


def fresh_record():
    """g_lx_fresh (section 5.11): the canonical record whose sha256 is index/ID."""
    h = lambda p: sha_file(p)  # noqa: E731
    return {"schema": "lx.fresh.v1", "commit": PIN, "tree": TREE, "sha256sums": h(os.path.join(META, "SHA256SUMS")),
            "ctags": h(CTAGS), "lx_macros": h(MACROS), "lx_nodes": h(os.path.join(TOOLS, "lx_nodes.py")),
            "book_builder": tool_digest(BUILDER_TOOLS)}


def fresh_id(rec=None):
    rec = rec or fresh_record()
    return sha256b(json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def validate(obj, schema_id):
    """hb.*.v2 validation through the vendored schemalib; returns a list of errors (empty = valid)."""
    return SL.validate(obj, schema_id)
