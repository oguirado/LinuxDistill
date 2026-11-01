# REPRODUCE — rebuild the exact Linux snapshot the lx router indexes

This repository ships NO Linux source (GPL-2.0, study-only). It ships the exact recipe to fetch the same bytes, and gates that prove you got them.
The router records (paths, sids, byte offsets, hashes) are valid only for this pin and this pattern set.

## What defines the snapshot
| File | Meaning |
|---|---|
| `spec/SPARSE.patterns` | no-cone sparse patterns (gitignore syntax); sha256 recorded in `rcu-free-v3@5495317/meta/PROVENANCE.json` (`patterns_sha256`) |
| `spec/EXPECT.paths` | the exact list of 8,182 files the snapshot must contain (measured independently from the GitHub tree API) |
| `spec/EXPECT.json` | expected count/bytes: 8,182 files, 89,370,484 B, plus `paths_sha256` |
| `rcu-free-v3@5495317/meta/ls-files.txt` | git blob id per file (gate A2) |
| `rcu-free-v3@5495317/meta/SHA256SUMS`, `MANIFEST.jsonl` | sha256 per file, licence, tier |

Pin: repository https://github.com/torvalds/linux.git, commit `549531755d329ec48439e3263535351ba1c5acd5`, tree `e56d24e86147e65a8ade3cfe69dee2bfdac279fa`. Never clone by branch name: the branch moves.

## Steps (needs git ≥ 2.25, python3, network to github.com; ~110 MB)
```bash
git clone <this repo> LinuxDistill && cd LinuxDistill
# keep the committed meta as the reference, rebuild into a fresh pin dir
mv rcu-free-v3@5495317 reference@5495317
sed -i "s#^ROOT=.*#ROOT=$PWD#" tools/lx_acquire.sh
bash tools/lx_acquire.sh            # A0 patterns applied verbatim, fetch by sha, A1 commit+tree, A2 blob ids, A4 count/bytes/paths vs spec/EXPECT, A5 exclusions
python3 -I tools/lx_a3.py rcu-free-v3@5495317    # A3 licence ruling (SPDX-less files inherit COPYING)
diff reference@5495317/meta/SHA256SUMS rcu-free-v3@5495317/meta/SHA256SUMS && echo "IDENTICAL SNAPSHOT"
```
`lx_acquire.sh` prints `LX_ACQUIRE_OK` only if every gate passes. A failed pin dir is deleted and re-acquired, never repaired in place.

## Rebuild the router on the snapshot
```bash
cp -r reference@5495317/router rcu-free-v3@5495317/router
bash rcu-free-v3@5495317/router/build.sh       # ~35 s; byte-identical outputs
bash rcu-free-v3@5495317/router/gates/run_all.sh   # 11/11 positive PASS, 11/11 must-FAIL as expected
```
Every `index/ID` must equal the g_lx_fresh digest in `router/REPORT.md`; any source byte that differs changes the ID, so a wrong snapshot can't pass silently.

## Notes
- DEV-LX-1: `meta/ls-files.txt` records only the checked-out (H) entries of the sparse index.
- The VMM corpora follow the same idea in the sibling repo DistroVMM (`tools/dv_acquire.py all`, pins in its PROVENANCE files).
