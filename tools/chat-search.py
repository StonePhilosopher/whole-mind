#!/usr/bin/env python3
"""Provenance-bearing FTS5 index for OpenClaw session logs.

This database is a derived search aid, never an archive. Updates are made on a
verified copy and atomically promoted; the previous database is preserved with
SQLite's backup API so WAL state is included.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

PROTOCOL_VERSION = "1.1"
SCHEMA_VERSION = 3
DEFAULT_SESSIONS = Path.home() / ".openclaw/agents/main/sessions"
DEFAULT_DB = Path.home() / ".openclaw/workspace/chat-search.db"


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output(value, json_mode):
    if json_mode:
        print(json.dumps(value, indent=2, sort_keys=True))


def candidates(root):
    if not root.is_dir():
        raise FileNotFoundError(f"session corpus not found: {root}")
    def is_session_log(path):
        name = path.name
        if ".codex-app-server.json.migrated" in name:
            return False
        return (
            name.endswith(".jsonl")
            or name.endswith(".jsonl.zst")
            or ".jsonl.deleted." in name
            or ".jsonl.reset." in name
            or ".jsonl.bak-" in name
        )

    return sorted(p for p in root.iterdir() if p.is_file() and is_session_log(p))


def session_lines(path):
    if path.suffix != ".zst":
        with path.open("r", errors="replace") as handle:
            yield from enumerate(handle, 1)
        return
    if not shutil.which("zstd"):
        raise RuntimeError("zstd is required to read compressed sessions")
    proc = subprocess.Popen(
        ["zstd", "-q", "-dc", "--", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )
    assert proc.stdout is not None
    stderr = ""
    try:
        for item in enumerate(proc.stdout, 1):
            yield item
    finally:
        proc.stdout.close()
        if proc.stderr:
            stderr = proc.stderr.read()
            proc.stderr.close()
    if proc.wait():
        raise RuntimeError(f"zstd failed for {path.name}: {stderr.strip()}")


def text_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def epoch(timestamp):
    try:
        value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    except (AttributeError, ValueError):
        return 0.0


def digest_file(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


@contextlib.contextmanager
def source_snapshot(path, directory):
    """Copy one stable source generation, hashing the exact bytes later parsed."""
    before = path.stat()
    suffix = ".zst" if path.suffix == ".zst" else ".jsonl"
    fd, name = tempfile.mkstemp(prefix=".chat-search-source-", suffix=suffix, dir=directory)
    snapshot = Path(name)
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as destination, path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
                destination.write(block)
            destination.flush()
            os.fsync(destination.fileno())
        after = path.stat()
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if identity_before != identity_after:
            raise RuntimeError(f"source changed while being indexed: {path.name}; retry index")
        yield snapshot, digest.hexdigest(), after
    finally:
        snapshot.unlink(missing_ok=True)


def connect(path, read_only=False):
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def schema_version(conn):
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        return int(row[0]) if row else None
    except (sqlite3.DatabaseError, ValueError):
        return None


def initialize(conn):
    conn.executescript(
        """
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE messages(
          id INTEGER PRIMARY KEY,
          message_key TEXT NOT NULL UNIQUE,
          session_id TEXT NOT NULL,
          message_id TEXT,
          timestamp TEXT,
          ts_epoch REAL NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('user','assistant')),
          content TEXT NOT NULL,
          content_sha256 TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE messages_fts USING fts5(
          content, role UNINDEXED, session_id UNINDEXED, timestamp UNINDEXED,
          content='messages', content_rowid='id'
        );
        CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
          INSERT INTO messages_fts(rowid,content,role,session_id,timestamp)
          VALUES(new.id,new.content,new.role,new.session_id,new.timestamp);
        END;
        CREATE TABLE sources(
          id INTEGER PRIMARY KEY,
          source_file TEXT NOT NULL,
          fingerprint TEXT NOT NULL,
          size INTEGER NOT NULL,
          mtime_ns INTEGER NOT NULL,
          compression TEXT NOT NULL,
          indexed_at TEXT NOT NULL,
          message_count INTEGER NOT NULL,
          malformed_lines INTEGER NOT NULL,
          UNIQUE(source_file,fingerprint)
        );
        CREATE TABLE source_paths(
          source_file TEXT PRIMARY KEY,
          current_source_id INTEGER NOT NULL REFERENCES sources(id),
          present INTEGER NOT NULL CHECK(present IN (0,1)),
          observed_size INTEGER,
          observed_mtime_ns INTEGER,
          last_seen_at TEXT NOT NULL
        );
        CREATE TABLE message_sources(
          message_id INTEGER NOT NULL REFERENCES messages(id),
          source_id INTEGER NOT NULL REFERENCES sources(id),
          source_line INTEGER NOT NULL,
          PRIMARY KEY(message_id,source_id,source_line)
        );
        CREATE INDEX message_sources_source ON message_sources(source_id);
        CREATE TABLE index_runs(
          id INTEGER PRIMARY KEY,
          started_at TEXT NOT NULL,
          finished_at TEXT NOT NULL,
          corpus_root TEXT NOT NULL,
          discovered_files INTEGER NOT NULL,
          indexed_files INTEGER NOT NULL,
          unchanged_files INTEGER NOT NULL,
          messages_added INTEGER NOT NULL,
          links_added INTEGER NOT NULL,
          malformed_lines INTEGER NOT NULL
        );
        """
    )
    stamp = now()
    conn.executemany(
        "INSERT INTO meta VALUES(?,?)",
        [
            ("schema_version", str(SCHEMA_VERSION)),
            ("protocol_version", PROTOCOL_VERSION),
            ("database_role", "derived_search_index"),
            ("authoritative", "false"),
            ("created_at", stamp),
            ("updated_at", stamp),
        ],
    )
    conn.commit()


def sqlite_backup(source, destination):
    source_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    destination_conn = sqlite3.connect(destination)
    try:
        source_conn.backup(destination_conn)
        destination_conn.commit()
    finally:
        source_conn.close()
        destination_conn.close()


def sqlite_backup_atomic(source, destination):
    """Create a complete backup under a temp name, then publish it atomically."""
    fd, name = tempfile.mkstemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    temporary.unlink()
    try:
        sqlite_backup(source, temporary)
        with connect(temporary, True) as conn:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("preserved-index backup failed integrity verification")
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def migrate_v2_to_v3(conn):
    conn.executescript(
        """
        ALTER TABLE message_sources RENAME TO message_sources_v2;
        CREATE TABLE message_sources(
          message_id INTEGER NOT NULL REFERENCES messages(id),
          source_id INTEGER NOT NULL REFERENCES sources(id),
          source_line INTEGER NOT NULL,
          PRIMARY KEY(message_id,source_id,source_line)
        );
        INSERT INTO message_sources SELECT message_id,source_id,source_line
          FROM message_sources_v2;
        DROP TABLE message_sources_v2;
        CREATE INDEX message_sources_source ON message_sources(source_id);
        """
    )
    conn.execute(
        "UPDATE meta SET value=? WHERE key='schema_version'", (str(SCHEMA_VERSION),)
    )
    conn.execute(
        "UPDATE meta SET value=? WHERE key='protocol_version'", (PROTOCOL_VERSION,)
    )


@contextlib.contextmanager
def locked(db_path):
    lock_path = db_path.with_name(db_path.name + ".lock")
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"another update holds {lock_path}") from error
        yield


def parse_source(path, source_name=None):
    session_id = (source_name or path.name).split(".", 1)[0]
    messages = []
    malformed = 0
    for line_number, line in session_lines(path):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(record, dict):
            continue
        if record.get("type") == "session" and record.get("id"):
            session_id = str(record["id"])
            continue
        if record.get("type") != "message" or not isinstance(record.get("message"), dict):
            continue
        message = record["message"]
        role = message.get("role")
        content = text_content(message.get("content"))
        if role not in ("user", "assistant") or len(content.strip()) < 2:
            continue
        timestamp = str(record.get("timestamp") or "")
        message_id = str(record.get("id") or "")
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        identity = (
            f"{session_id}\0{message_id}\0{content_hash}"
            if message_id
            else f"{session_id}\0{timestamp}\0{role}\0{content_hash}"
        )
        messages.append(
            (
                hashlib.sha256(identity.encode()).hexdigest(),
                session_id,
                message_id or None,
                timestamp,
                epoch(timestamp),
                role,
                content,
                content_hash,
                line_number,
            )
        )
    return messages, malformed


def add_source(conn, path, source_name, fingerprint, stat):
    messages, malformed = parse_source(path, source_name)
    source_id = conn.execute(
        """INSERT INTO sources
           (source_file,fingerprint,size,mtime_ns,compression,indexed_at,
            message_count,malformed_lines) VALUES(?,?,?,?,?,?,?,?)""",
        (
            source_name,
            fingerprint,
            stat.st_size,
            stat.st_mtime_ns,
            "zstd" if path.suffix == ".zst" else "plain",
            now(),
            len(messages),
            malformed,
        ),
    ).lastrowid
    added = links = 0
    for values in messages:
        line_number = values[-1]
        cursor = conn.execute(
            "INSERT INTO messages VALUES(NULL,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(message_key) DO NOTHING",
            values[:-1],
        )
        added += cursor.rowcount == 1
        message_pk = conn.execute(
            "SELECT id FROM messages WHERE message_key=?", (values[0],)
        ).fetchone()[0]
        cursor = conn.execute(
            "INSERT INTO message_sources VALUES(?,?,?) "
            "ON CONFLICT(message_id,source_id,source_line) DO NOTHING",
            (message_pk, source_id, line_number),
        )
        links += cursor.rowcount == 1
    conn.execute(
        """INSERT INTO source_paths VALUES(?,?,1,?,?,?)
           ON CONFLICT(source_file) DO UPDATE SET
             current_source_id=excluded.current_source_id,present=1,
             observed_size=excluded.observed_size,
             observed_mtime_ns=excluded.observed_mtime_ns,
             last_seen_at=excluded.last_seen_at""",
        (source_name, source_id, stat.st_size, stat.st_mtime_ns, now()),
    )
    return int(added), int(links), malformed


def verify(conn):
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    fts_rows = conn.execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0]
    foreign_keys = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    if integrity != "ok" or messages != fts_rows or foreign_keys:
        raise RuntimeError(
            f"verification failed: integrity={integrity}, messages={messages}, "
            f"fts={fts_rows}, foreign_keys={foreign_keys}"
        )
    return {"integrity": integrity, "messages": messages, "fts_rows": fts_rows,
            "foreign_key_errors": foreign_keys}


def index(db_path, root, json_mode=False, verify_sources=False):
    db_path = db_path.resolve()
    root = root.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    files = candidates(root)
    started = now()
    clock = time.monotonic()
    with locked(db_path):
        fd, name = tempfile.mkstemp(prefix=".chat-search-candidate-", dir=db_path.parent)
        os.close(fd)
        candidate = Path(name)
        candidate.unlink()
        legacy = False
        migrated_schema = False
        had_current_schema = False
        try:
            if db_path.exists():
                with connect(db_path, True) as current:
                    current_version = schema_version(current)
                if current_version in (2, SCHEMA_VERSION):
                    had_current_schema = current_version == SCHEMA_VERSION
                    sqlite_backup(db_path, candidate)
                    if current_version == 2:
                        with connect(candidate) as conn:
                            migrate_v2_to_v3(conn)
                            conn.commit()
                        migrated_schema = True
                else:
                    legacy = True
                    with connect(candidate) as conn:
                        initialize(conn)
            else:
                with connect(candidate) as conn:
                    initialize(conn)
            conn = connect(candidate)
            indexed = unchanged = added = links = malformed = 0
            path_state_changed = migrated_schema
            try:
                conn.execute("BEGIN IMMEDIATE")
                previously_present = {
                    row[0]
                    for row in conn.execute(
                        "SELECT source_file FROM source_paths WHERE present=1"
                    )
                }
                observed_names = {path.name for path in files}
                presence_changed = previously_present != observed_names
                conn.execute("UPDATE source_paths SET present=0")
                for path in files:
                    stat = path.stat()
                    current = conn.execute(
                        """SELECT p.observed_size,p.observed_mtime_ns FROM source_paths p
                           JOIN sources s ON s.id=p.current_source_id
                           WHERE p.source_file=?""",
                        (path.name,),
                    ).fetchone()
                    if (
                        current
                        and current[0] == stat.st_size
                        and current[1] == stat.st_mtime_ns
                        and not verify_sources
                    ):
                        unchanged += 1
                        conn.execute(
                            """UPDATE source_paths SET present=1,observed_size=?,
                               observed_mtime_ns=?,last_seen_at=? WHERE source_file=?""",
                            (stat.st_size, stat.st_mtime_ns, now(), path.name),
                        )
                        continue
                    with source_snapshot(path, db_path.parent) as (
                        snapshot, fingerprint, stable_stat
                    ):
                        prior = conn.execute(
                            "SELECT id FROM sources WHERE source_file=? AND fingerprint=?",
                            (path.name, fingerprint),
                        ).fetchone()
                        if prior:
                            unchanged += 1
                            path_state_changed = path_state_changed or not (
                                current
                                and current[0] == stable_stat.st_size
                                and current[1] == stable_stat.st_mtime_ns
                            )
                            conn.execute(
                                """INSERT INTO source_paths VALUES(?,?,1,?,?,?)
                                   ON CONFLICT(source_file) DO UPDATE SET
                                     current_source_id=excluded.current_source_id,present=1,
                                     observed_size=excluded.observed_size,
                                     observed_mtime_ns=excluded.observed_mtime_ns,
                                     last_seen_at=excluded.last_seen_at""",
                                (path.name, prior[0], stable_stat.st_size,
                                 stable_stat.st_mtime_ns, now()),
                            )
                            continue
                        new_added, new_links, bad = add_source(
                            conn, snapshot, path.name, fingerprint, stable_stat
                        )
                    indexed += 1
                    path_state_changed = True
                    added += new_added
                    links += new_links
                    malformed += bad
                finished = now()
                conn.execute("UPDATE meta SET value=? WHERE key='updated_at'", (finished,))
                conn.execute(
                    "INSERT INTO index_runs VALUES(NULL,?,?,?,?,?,?,?,?,?)",
                    (started, finished, str(root), len(files), indexed, unchanged,
                     added, links, malformed),
                )
                conn.commit()
                checks = verify(conn)
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

            promoted = not (
                had_current_schema and indexed == 0 and not presence_changed
                and not path_state_changed
            )
            preserved = None
            if promoted:
                with connect(candidate) as candidate_conn:
                    candidate_conn.execute("PRAGMA journal_mode=DELETE")
                    candidate_conn.commit()
                for suffix in ("-wal", "-journal"):
                    sidecar = Path(str(db_path) + suffix)
                    if sidecar.exists() and sidecar.stat().st_size:
                        raise RuntimeError(
                            f"refusing promotion beside non-empty SQLite sidecar: {sidecar}"
                        )
                if db_path.exists():
                    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    preserved = db_path.with_name(f"{db_path.name}.pre-index-{stamp}")
                    serial = 1
                    while preserved.exists():
                        preserved = db_path.with_name(
                            f"{db_path.name}.pre-index-{stamp}-{serial}"
                        )
                        serial += 1
                    sqlite_backup_atomic(db_path, preserved)
                with candidate.open("rb") as handle:
                    os.fsync(handle.fileno())
                os.replace(candidate, db_path)
                directory_fd = os.open(db_path.parent, os.O_DIRECTORY)
                os.fsync(directory_fd)
                os.close(directory_fd)
        finally:
            candidate.unlink(missing_ok=True)

    result = {
        "ok": True,
        "operation": "index",
        "protocol_version": PROTOCOL_VERSION,
        "schema_version": SCHEMA_VERSION,
        "database_role": "derived_search_index",
        "authoritative": False,
        "database": str(db_path),
        "corpus_root": str(root),
        "discovered_files": len(files),
        "indexed_files": indexed,
        "unchanged_files": unchanged,
        "messages_added": added,
        "provenance_links_added": links,
        "malformed_lines": malformed,
        "migrated_from_legacy": legacy,
        "migrated_schema": migrated_schema,
        "verified_sources": verify_sources,
        "preserved_previous_index": str(preserved) if preserved else None,
        "promoted": promoted,
        "no_changes": not promoted,
        "verification": checks,
        "elapsed_seconds": round(time.monotonic() - clock, 3),
    }
    if not json_mode:
        print(f"Indexed {indexed} changed/new files; {unchanged} unchanged.")
        print(f"Messages: {checks['messages']:,} total; {added:,} newly discovered.")
        print("Role: derived search index (not an archive or backup).")
        if not promoted:
            print("No corpus changes; verified candidate discarded without creating a backup.")
        elif preserved:
            print(f"Preserved previous index: {preserved}")
        if promoted:
            print(f"Verified and promoted: {db_path}")
    output(result, json_mode)
    return result


def require_index(path):
    if not path.exists():
        raise FileNotFoundError(f"no index found at {path}; run index")
    conn = connect(path, True)
    if schema_version(conn) != SCHEMA_VERSION:
        conn.close()
        raise RuntimeError("legacy index schema; run index to migrate safely")
    return conn


def describe(json_mode=False):
    value = {
        "name": "openclaw-chat-search",
        "protocol_version": PROTOCOL_VERSION,
        "schema_version": SCHEMA_VERSION,
        "database_role": "derived_search_index",
        "authoritative": False,
        "source_of_truth": "OpenClaw session-log files in the configured corpus root",
        "operations": ["describe", "status", "index", "search", "stats"],
        "limits": {
            "roles": ["user", "assistant"],
            "search_limit_max": 500,
            "query_syntax": "SQLite FTS5 MATCH syntax",
            "date_filter_timezone": "UTC",
            "platform": "POSIX host with SQLite FTS5; zstd executable for compressed logs",
        },
        "safety": {
            "updates": "copy-on-write with atomic promotion",
            "previous_index": "SQLite online backup",
            "promotion_checks": ["integrity", "foreign_keys", "FTS parity"],
            "missing_sources": "retained and reported, never silently pruned",
        },
    }
    if not json_mode:
        print(f"OpenClaw Chat Search protocol {PROTOCOL_VERSION}")
        print("Derived FTS5 search index; not an archive or backup.")
        print("Operations: describe, status, index, search, stats")
    output(value, json_mode)
    return value


def status(db_path, root, verify_sources=False, json_mode=False, emit_result=True):
    root_available = root.is_dir()
    observed = {path.name: path for path in candidates(root)} if root_available else {}
    conn = require_index(db_path)
    try:
        rows = conn.execute(
            """SELECT p.source_file,s.fingerprint,p.observed_size,p.observed_mtime_ns
               FROM source_paths p JOIN sources s ON s.id=p.current_source_id"""
        ).fetchall()
        indexed = {row[0]: row for row in rows}
        new_files, changed_files, current_files = [], [], []
        for name, path in observed.items():
            row = indexed.get(name)
            if not row:
                new_files.append(name)
                continue
            stat = path.stat()
            same = row[2] == stat.st_size and row[3] == stat.st_mtime_ns
            if same and verify_sources:
                same = row[1] == digest_file(path)
            (current_files if same else changed_files).append(name)
        missing_files = sorted(set(indexed) - set(observed))
        present_fingerprints = {
            indexed[name][1] for name in observed if name in indexed
        }
        superseded_files = sorted(
            name for name in missing_files if indexed[name][1] in present_fingerprints
        )
        missing_files = sorted(set(missing_files) - set(superseded_files))
        coverage = conn.execute(
            """SELECT COUNT(*),COUNT(DISTINCT session_id),
                      MIN(NULLIF(timestamp,'')),MAX(NULLIF(timestamp,''))
               FROM messages"""
        ).fetchone()
        undated = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE timestamp='' OR timestamp IS NULL"
        ).fetchone()[0]
        updated = conn.execute(
            "SELECT value FROM meta WHERE key='updated_at'"
        ).fetchone()[0]
        revisions = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    finally:
        conn.close()
    freshness = (
        "unknown" if not root_available
        else "current" if not new_files and not changed_files else "stale"
    )
    source_health = (
        "unavailable" if not root_available
        else "complete" if not missing_files else "degraded"
    )
    value = {
        "ok": True,
        "operation": "status",
        "database_role": "derived_search_index",
        "authoritative": False,
        "freshness": freshness,
        "source_health": source_health,
        "index_updated_at": updated,
        "coverage": {
            "messages": coverage[0],
            "undated_messages": undated,
            "sessions": coverage[1],
            "oldest_message": coverage[2],
            "newest_message": coverage[3],
            "source_paths": len(indexed),
            "source_revisions": revisions,
        },
        "sources": {
            "observed": len(observed),
            "current": len(current_files),
            "new": len(new_files),
            "changed": len(changed_files),
            "missing_but_retained": len(missing_files),
            "superseded_paths": len(superseded_files),
            "verified_by_hash": verify_sources,
            "new_files": sorted(new_files),
            "changed_files": sorted(changed_files),
            "missing_files": missing_files,
            "superseded_files": superseded_files,
        },
        "next_actions": (
            (["restore corpus access"] if not root_available else [])
            + (["run index"] if freshness == "stale" else [])
            + (["locate or restore missing original session logs"] if missing_files else [])
        ),
        "warning": "Missing original logs cannot be restored from this derived index.",
    }
    if emit_result and not json_mode:
        print(f"Index freshness: {freshness.upper()}")
        print(f"Source health: {source_health.upper()}")
        print("Role: derived search index (not an archive or backup)")
        print(f"Coverage: {coverage[0]:,} messages / {coverage[1]:,} sessions")
        print(f"Dates: {coverage[2] or '?'} -> {coverage[3] or '?'}")
        print(
            f"Corpus: {len(observed)} observed; {len(new_files)} new; "
            f"{len(changed_files)} changed; {len(missing_files)} missing but retained"
        )
        if freshness == "stale":
            print("Next action: run index")
        print(value["warning"])
    if emit_result:
        output(value, json_mode)
    return value


def search(
    db_path, query, limit=20, role=None, after=None, before=None,
    json_mode=False, root=None
):
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    conn = require_index(db_path)
    sql = """SELECT m.id,m.timestamp,m.role,
                    snippet(messages_fts,0,'>>>','<<<','...',40),
                    m.session_id,m.message_id,m.content_sha256
             FROM messages_fts JOIN messages m ON m.id=messages_fts.rowid
             WHERE messages_fts MATCH ?"""
    params = [query]
    if role:
        sql += " AND m.role=?"
        params.append(role)
    if after:
        sql += " AND m.ts_epoch>=?"
        params.append(
            datetime.strptime(after, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
        )
    if before:
        sql += " AND m.ts_epoch<?"
        params.append(
            datetime.strptime(before, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
        )
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    try:
        rows = conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            evidence = conn.execute(
                """SELECT s.source_file,x.source_line,
                          CASE WHEN p.current_source_id=s.id THEN 1 ELSE 0 END,
                          COALESCE(p.present,0)
                   FROM message_sources x JOIN sources s ON s.id=x.source_id
                   LEFT JOIN source_paths p ON p.source_file=s.source_file
                   WHERE x.message_id=? ORDER BY 3 DESC,s.indexed_at DESC""",
                (row[0],),
            ).fetchall()
            results.append(
                {
                    "timestamp": row[1],
                    "role": row[2],
                    "snippet": row[3].replace("\n", " ").strip(),
                    "session_id": row[4],
                    "message_id": row[5],
                    "content_sha256": row[6],
                    "evidence": [
                        {"source_file": item[0], "source_line": item[1],
                         "indexed_current_revision": bool(item[2]),
                         "source_present_at_last_index": bool(item[3])}
                        for item in evidence
                    ],
                }
            )
    finally:
        conn.close()
    index_state = status(db_path, root, False, True, False) if root else None
    value = {"ok": True, "operation": "search", "query": query,
             "result_count": len(results), "results": results,
             "database_role": "derived_search_index", "authoritative": False,
             "index_status": (
                 {"freshness": index_state["freshness"],
                  "source_health": index_state["source_health"],
                  "index_updated_at": index_state["index_updated_at"]}
                 if index_state else {"freshness": "not_checked"}
             )}
    if not json_mode:
        if index_state and index_state["freshness"] != "current":
            print("WARNING: index is stale; run index before treating absence as evidence.\n")
        if index_state and index_state["source_health"] != "complete":
            print("WARNING: one or more original source logs are missing.\n")
        print(f"Found {len(results)} result(s):\n" if results else "No results found.")
        for item in results:
            snippet = item["snippet"][:240] + ("..." if len(item["snippet"]) > 240 else "")
            print(f"[{item['timestamp'] or '?'}] {item['role']}: {snippet}")
            print(f"  session: {item['session_id']}")
            if item["evidence"]:
                source = item["evidence"][0]
                print(f"  evidence: {source['source_file']}:{source['source_line']}")
            print()
    output(value, json_mode)
    return value


def stats(db_path, json_mode=False):
    conn = require_index(db_path)
    try:
        total, sessions, oldest, newest = conn.execute(
            """SELECT COUNT(*),COUNT(DISTINCT session_id),
                      MIN(NULLIF(timestamp,'')),MAX(NULLIF(timestamp,''))
               FROM messages"""
        ).fetchone()
        undated = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE timestamp='' OR timestamp IS NULL"
        ).fetchone()[0]
        roles = dict(conn.execute("SELECT role,COUNT(*) FROM messages GROUP BY role"))
        paths = conn.execute("SELECT COUNT(*) FROM source_paths").fetchone()[0]
        revisions = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    finally:
        conn.close()
    value = {"ok": True, "operation": "stats", "messages": total,
             "undated_messages": undated,
             "sessions": sessions, "roles": roles, "oldest_message": oldest,
             "newest_message": newest, "source_paths": paths,
             "source_revisions": revisions, "database_role": "derived_search_index",
             "authoritative": False}
    if not json_mode:
        print(f"Messages/sessions: {total:,}/{sessions:,}")
        print(f"Dates: {oldest or '?'} -> {newest or '?'}")
        print(f"Source paths/revisions: {paths:,}/{revisions:,}")
        print("Role: derived search index (not an archive or backup)")
    output(value, json_mode)
    return value


def make_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--sessions-dir", type=Path, default=DEFAULT_SESSIONS)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("describe", "describe protocol and semantics"),
        ("index", "safely update the index"),
        ("stats", "show index statistics"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--json", action="store_true")
        if name == "index":
            command.add_argument("--verify-sources", action="store_true")
    command = commands.add_parser("status", help="show freshness and source coverage")
    command.add_argument("--verify-sources", action="store_true")
    command.add_argument("--json", action="store_true")
    command = commands.add_parser("search", help="search indexed messages")
    command.add_argument("query")
    command.add_argument("--limit", "-n", type=int, default=20)
    command.add_argument("--role", "-r", choices=["user", "assistant"])
    command.add_argument("--after", "-a")
    command.add_argument("--before", "-b")
    command.add_argument("--json", action="store_true")
    return parser


def main(argv=None):
    args = make_parser().parse_args(argv)
    try:
        if args.command == "describe":
            describe(args.json)
        elif args.command == "index":
            index(args.db, args.sessions_dir, args.json, args.verify_sources)
        elif args.command == "status":
            status(args.db, args.sessions_dir, args.verify_sources, args.json)
        elif args.command == "search":
            search(
                args.db, args.query, args.limit, args.role, args.after,
                args.before, args.json, args.sessions_dir
            )
        elif args.command == "stats":
            stats(args.db, args.json)
    except (OSError, RuntimeError, ValueError, sqlite3.DatabaseError) as error:
        value = {"ok": False, "operation": args.command,
                 "error": {"type": type(error).__name__, "message": str(error)}}
        if getattr(args, "json", False):
            print(json.dumps(value, indent=2, sort_keys=True))
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
