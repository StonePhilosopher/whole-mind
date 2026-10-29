# Chat Fossil Record — Independent Review Ledger

Status: **revision 1.1 repaired locally; independent re-verification pending**

This ledger makes the tool's review history available to another agent without
sharing any private session logs or search databases.

## What was independently established

Marey reviewed revision 1.0 on Linux/Python 3.12 and O.C. reviewed it on
macOS/Python 3.14. Both used only synthetic fixtures. Both found that the core
safety boundary held: corrupt input and failed updates did not replace the live
database, SQLite's backup API captured WAL-resident prior state, and the
copy-on-write candidate was verified before promotion.

They also found defects in the incremental and reporting layers. Revision 1.1
contains a regression test and repair for each reported class:

| Finding | Revision 1.1 repair |
|---|---|
| Metadata-only change left freshness permanently stale | Promote changed `source_paths` state even when content matches a prior revision |
| Same-size/same-mtime content drift could be detected but not repaired | Added `index --verify-sources` |
| WAL sidecars could overlay a promoted main file | Normalize candidate to DELETE journal mode and refuse promotion beside a non-empty live WAL/journal |
| Missing corpus root made retained text unsearchable | Search remains available; status reports freshness `unknown` and source health `unavailable` |
| Date filters and naive timestamps depended on host timezone | All date interpretation is explicitly UTC |
| Undated messages disappeared from summary counts | Count all messages and report `undated_messages` separately |
| Some I/O failures escaped the JSON protocol | Catch `OSError` and return structured failure |
| Failed preservation could leave a zero-byte backup | Write and verify a temporary backup, then atomically rename |
| Duplicate records in one source lost later line pointers | Schema v3 keys provenance by message, source revision, and source line |
| Hash and parse could observe different source generations | Snapshot once; hash and parse the same bytes; abort if the source changes during capture |
| Discovery/documentation seams were ambiguous | Include `.jsonl.zst`, exclude migration metadata, and publish FTS5/UTC/POSIX limits in `describe` |

## Current local evidence

- `python3 -m unittest -v tests/test_chat_search.py`: **16/16 pass**.
- A disposable migration of the real schema-v2 index to schema v3 completed
  successfully with source hashing enabled.
- The migrated candidate reported SQLite integrity `ok`, zero foreign-key
  errors, and exact parity between 9,488 message rows and 9,488 FTS rows.
- The private corpus and resulting database are not part of this repository.

These are author-side results, not independent proof of revision 1.1.

## Requested second-pass verification

From a clean checkout, use synthetic data only unless you deliberately choose a
local corpus:

```bash
python3 -m unittest -v tests/test_chat_search.py
python3 tools/chat-search.py describe --json
```

Then attack the repaired seams. In particular:

1. Try to mutate or replace the live database through a failed update.
2. Reproduce WAL-mode promotion with an external connection and confirm the
   operation refuses safely or cannot replay stale frames.
3. Repeat one id-less message at multiple lines and verify every line pointer is
   retained without multiplying the searchable message.
4. Preserve size and mtime while changing content; verify default status remains
   advisory, `status --verify-sources` detects drift, and
   `index --verify-sources` repairs it.
5. Modify a source during capture and verify the index aborts without promotion.
6. Remove the corpus root and verify retained search remains usable with honest
   `unknown`/`unavailable` state.
7. Exercise malformed FTS5, permission, corrupt zstd, timestamp, and oversized
   input errors through `--json`.
8. Inspect the schema-v2 to schema-v3 migration and confirm existing provenance
   survives.

Return environment, exact commands, a `PASS`, `DEFECT`, or `QUESTION` verdict,
the smallest reproducer for every defect, and whether a proposed repair changes
the contract or only its implementation.
