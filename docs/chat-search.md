# Chat Fossil Record

`tools/chat-search.py` builds a local SQLite FTS5 index over OpenClaw's session-log
corpus. The index is a **derived search instrument**, not an archive or backup.
If an original session file disappears, the indexed text may remain searchable,
but the tool cannot reconstruct the original JSONL record or its full metadata.

## Agent protocol

Every operation supports `--json` and reports stable semantics:

```bash
python3 tools/chat-search.py describe --json
python3 tools/chat-search.py status --verify-sources --json
python3 tools/chat-search.py index --json
python3 tools/chat-search.py index --verify-sources --json
python3 tools/chat-search.py search 'TN397' --limit 10 --json
python3 tools/chat-search.py stats --json
```

`describe` is the discovery surface. `status` separates index freshness from
source health: an index can match the currently observed corpus while still
reporting original source files that have gone missing.

Search results contain stable session/message identifiers, a content hash, and
one or more evidence pointers of the form `source_file` + `source_line`.
Duplicate copies of the same message are collapsed while retaining every source
pointer, including repeated records at different lines in one file. Search also
reports index freshness and source health; stale searches
warn before displaying results so an absence is not silently treated as evidence.

Queries use SQLite FTS5 `MATCH` syntax. `--after` and `--before` dates are UTC.
The default freshness check compares size and nanosecond mtime; use
`status --verify-sources` to hash every observed source, and
`index --verify-sources` to repair content drift hidden behind preserved file
metadata.

## Update and recovery contract

Indexing is incremental and copy-on-write:

1. Copy the current schema-v2 database with SQLite's online backup API, or create
   a fresh candidate when migrating a legacy database.
2. Snapshot each new or changed source once, hash and parse those exact bytes,
   and abort if the source changes during capture. Preserve prior source
   revisions and messages whose original files are no longer present.
3. Verify SQLite integrity, foreign keys, and exact FTS/message row parity.
4. Preserve the previous live index as
   `chat-search.db.pre-index-YYYYMMDD-HHMMSS`.
5. Normalize the candidate to SQLite DELETE-journal mode, refuse promotion
   beside a non-empty live `-wal` or rollback journal, and atomically promote the
   verified candidate.

If no source or source-presence state changed, the verified candidate is
discarded without promotion or another backup copy.

A malformed changed compressed archive aborts the update before promotion. The
existing live database remains intact.

All unreadable-source and I/O failures are fail-closed: the candidate is removed,
the live index is untouched, and `--json` returns a structured error. A missing
corpus root does not make retained text unsearchable; status reports freshness
`unknown` and source health `unavailable` until corpus access returns.

Pre-index copies are full databases and are created atomically. The tool does not
prune them; retention is an operator policy.

## Corpus boundary

Recognized session strata are live `.jsonl` files and OpenClaw's `.deleted`,
`.reset`, and `.bak` JSONL variants, plus `.jsonl.zst` and other recognized zstd
archives. Migration metadata
files such as `*.jsonl.codex-app-server.json.migrated` are deliberately excluded:
they describe runtime migration state and are not conversation logs.

## Verification

```bash
python3 -m unittest -v tests/test_chat_search.py
```

The fixtures cover initial indexing, incremental revision, duplicate provenance
within and across sources, metadata-only changes, verified-source repair,
missing-source and missing-root retention, UTC dates, undated counts, bounded
inputs, WAL-sidecar refusal, atomic backup failure, structured I/O errors,
discovery boundaries, and fail-closed corrupt-archive handling.

## Platform boundary

The implementation targets POSIX hosts and requires Python's SQLite build to
include FTS5. It uses `fcntl.flock`, directory fsync, and same-filesystem
`os.replace`; reading compressed logs additionally requires the `zstd`
executable. These constraints are reported by `describe --json`.
