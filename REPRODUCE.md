# Reproduce

This repository ships no Linux source. It ships the recipe to fetch the same bytes and the gates that prove you got them. Router records are valid only for this pin and pattern set. [README.md](README.md) explains what everything means.

## One command

Needs `git` 2.25 or later, `python3`, Universal Ctags at `/usr/bin/ctags`, `zstd`, network access to github.com and about 610 MB of disk.

```bash
git clone https://github.com/oguirado/LinuxDistill.git
cd LinuxDistill
bash tools/bootstrap.sh
```

The script stops at the first failure. The first two markers appear only on the first run, because an existing `src/` is kept and not re-verified. In order, it prints:

| Marker | Meaning |
|---|---|
| `LX_ACQUIRE_OK` | Gates A0 to A5 passed on the fetched snapshot |
| `SNAPSHOT_IDENTICAL` | Its `SHA256SUMS` equals the committed one, byte for byte |
| (no marker, silent on success) | Study files match `study/pass1/SHA256SUMS` |
| `{"summary": {"positive_pass": 11, "must_fail_as_expected": 11, "gates": 11}}` | Router gates passed |
| `{"gate": "G-LX-KNOW", ..., "pass": true}` | Knowledge layer rebuilt identically |
| `BOOTSTRAP_OK` | Everything passed |

Then run `git status --short`. It should list at most `rcu-free-v3@5495317/router/BUILD_TIMES.json`, which holds wall times. The index id includes the sha256 of the ctags binary, so with another ctags build these files change too: `router/dist/router/SHA256SUMS`, `router/dist/router/shards.jsonl`, `router/fixtures/score_ref_lx.json` and `router/knowledge/stats.json`. Any other change needs investigation.

## What defines the snapshot

| File | Meaning |
|---|---|
| `spec/SPARSE.patterns` | No-cone sparse patterns; the sha256 is in `meta/PROVENANCE.json` |
| `spec/EXPECT.paths` | The exact list of 8,182 files, measured independently from the GitHub tree API |
| `spec/EXPECT.json` | Expected count and bytes: 8,182 files, 89,370,484 B |
| `rcu-free-v3@5495317/meta/ls-files.txt` | Git blob id per file (gate A2). Only checked-out entries of the sparse index are listed |
| `rcu-free-v3@5495317/meta/SHA256SUMS`, `MANIFEST.jsonl` | sha256, licence and tier per file |

Pin: `https://github.com/torvalds/linux.git`, commit `549531755d329ec48439e3263535351ba1c5acd5`, tree `e56d24e86147e65a8ade3cfe69dee2bfdac279fa`. It is fetched by commit id, never by branch name.

## Rebuild parts

```bash
bash rcu-free-v3@5495317/router/build.sh                      # router, about 35 s
bash rcu-free-v3@5495317/router/gates/run_all.sh              # all router gates
python3 -I -B rcu-free-v3@5495317/router/tools/lx_knowledge.py build
python3 -I -B rcu-free-v3@5495317/router/tools/lx_knowledge.py check    # rebuilds, so it writes outputs
```

To re-acquire, make `src/` writable, delete it and run `tools/bootstrap.sh` again:

```bash
chmod -R u+w rcu-free-v3@5495317/src
rm -rf rcu-free-v3@5495317/src
bash tools/bootstrap.sh
```
