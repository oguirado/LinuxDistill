# lx router — BT-LXR-01..11 report (2026-11-01)

Built by an Opus lobe; gates re-run by the orchestrator: `bash gates/run_all.sh` rc 0, 11/11 positive PASS, 11/11 must-FAIL FAIL-as-expected, 0 DEAD, ~50 s [MEASURED].
`build.sh` rebuilds everything in ~35 s. A second full build (cwd `/`, different TZ and PYTHONHASHSEED) was byte-identical (lobe report).
Spot check by the orchestrator: IMPACT-13 gold (3 callers of `autogroup_kref_get`) confirmed by grep.

## Numbers [MEASURED]
- FILE layer: 8,029 nodes from a pool of 8,182.
- Header closure: 1,681 headers (13.37 MB); SYMBOL layer 51.38 MB against the 60 MB cap; nothing cut.
- Unresolved includes: 4.33 % of 32,571 include edges (trigger for `make prepare`: 5 %).
- Symbols: 138,451 records, 91,472 router nodes; 12-hex node ids, 0 collisions.
  Per book: inc 59,662 · x86 21,752 · kcore 14,286 · kvm 8,887 · mm 8,423 · a64 8,319 · boot 5,276 · sched 3,694 · dev 2,929 · time 1,502 · rcu 1,476 · locking 1,383 · irq 862.
- Edges: CALLS 203,147 · INCLUDES 26,578 · PHASE 14,478 · KCONFIG 3,197 · OPS 2,924 · ARCH_PAIR 1,132 · BUILT_BY 845.
- Unresolved: 30,757 call sites across 14,808 symbols; 488 OPS; 48 Makefile objects without a source file (kept with their coordinates). 305 symbols have fan-in > 64.
- Index: 14 directories, 27,508,476 B. Every `index/ID` = g_lx_fresh digest `fc102058…dba4` (recomputed for release 0.0.1, when the engine was bundled under `vendor/`; the record counts did not change).
- Shards: 14 `.tar.zst`, 44,371,146 B. Unpack + re-query gives the same answer sha on 32/32 rows.
- G-LX-CONF: 32 rows, all PASS (12 FIND, 6 IMPACT, 4 ARCHPAIR, 4 KCONFIG, 6 ABSENT). Gold comes from GNU grep and Makefile lines.
  Must-FAIL: constant router, stale index ID, `__anon` sid.

## Deviations
1. Clean room: the node title is the path and the purpose a generated line; the first comment is kept only as a byte span, and the C signature only as a hash.
2. The schema's kind list is closed, so C kinds are mapped onto it; the original kind is kept in idmap. The AST hash is replaced by a hash of the comment-free token stream.
3. FILE family is assigned by path prefix; headers outside the closure stay in lx-inc.
4. BT-LXR-02 uses the BT-LXR-01 macro table to find anchors (a dependency the paper does not list).
5. The asm label rule also accepts the `SYM_*START*` variants.
6. BT-LXR-06's positive control uses `CONFIG_VIRTIO_MMIO → virtio_mmio.c`, because drivers/block Makefile/Kconfig are not in the sparse set.
7. The g_lx_fresh "book builder" input is a digest over the 8 builder tools.
8. spec/PHASEMAP.tsv is written from the §1.3 draft; PHASE edges point to HB-KPAPER-001/hb-s5.p14.
9. CALLS resolution: same file, then the caller's book, then lx-inc; candidates from the other architecture are dropped.
10. Index weights, abstention rules and zstd level 9 are [TARGET-CHOSEN].
11. Grep cross-check drops lines that start with a comment marker. 12 FIND rows instead of 10.

## Blocked / absent
- T2-R catalogue nodes and ABSENT-with-coordinates answers: no T2-R rows on disk (they need the tree API).
- `CONFIG_VIRTIO_BLK → drivers/block/virtio_blk.c`: not in the sparse snapshot; recorded ABSENT.
- Not in scope here: the LX-DOSSIER class, source/meta shards (BT-LX-07/08), the VM leg of FT-LX0, gate-registry argv, schemas of the intermediate formats.

Derived outputs (index, dist, hb, graph, nodes, closure, routes) are untracked and reproducible by build.sh; tools, gates, fixtures, BUILD_TIMES and the shard SHA256SUMS are tracked.

## Knowledge layer (2026-11-01) — `tools/lx_knowledge.py`
Deterministic index of the APPROVED study pass 1 (`study/pass1/`, 2,628 files, SHA256SUMS). No model in the loop.
- 111,144 finding nodes: 89,089 extract, 20,974 partial, 1,081 dossier. 347,660 CITES edges to router sids; 8,989 DERIVES edges; 46 unresolved citations listed in `knowledge/unresolved.jsonl`.
- Review flags: Argon round-2 verdicts are attached to the 136 sampled dossier findings (64 SUPPORTED, 71 PARTIAL, 1 UNSUPPORTED); every other node is "unreviewed".
- Index `index/lx-knowledge/` (lx.index.v1, integer BM25F; fields text, kind, sid, dossier). ID = sha256(study SHA256SUMS + g_lx_fresh).
- `lx_knowledge.py query "<text>" [--level dossier]` returns specification findings first, with their code locations (path@start-end bytes).
- Gate G-LX-KNOW PASS: rebuild byte-identical, 0 unresolved CITES edges. Must-FAIL legs: a tampered index ⇒ E_CHUNK_SHA; a changed study file ⇒ new ID.
