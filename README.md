# LinuxDistill — corpus lx (LINUX_DISTILL_STRATEGY_v1 §3.3)

Pinned sparse snapshot of torvalds/linux at commit 549531755d329ec48439e3263535351ba1c5acd5 (branch rcu-free-v3, tree e56d24e8…).
STUDY corpus under the STRICT clean room (LX §4): GPL source is never copied into our kernel. `*/src/` is read-only and untracked.

- spec/SPARSE.patterns: the paper's p3_sparse.py tiers, plus the 2 irqchip headers read from the tree API (BT-SEL-1).
- spec/EXPECT.json and EXPECT.paths: the kept set measured independently from the GitHub tree API (gate A4).
- tools/lx_acquire.sh: BT-LX-01. DEV-LX-1: ls-files records only the checked-out (H) entries of the sparse index.
- rcu-free-v3@5495317/meta/: PROVENANCE, ls-files, SHA256SUMS, MANIFEST.jsonl, GATES.json.
  A0, A1, A2, A4 and A5 PASS. A3 PASS by ruling (tools/lx_a3.py, meta/A3.json): files without SPDX inherit the root COPYING licence (GPL-2.0 WITH Linux-syscall-note); LICENSES/* are licence texts; all lx files are Z-STUDY STRICT.
