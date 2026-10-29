import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "tools/chat-search.py"
SPEC = importlib.util.spec_from_file_location("chat_search", MODULE_PATH)
chat_search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(chat_search)


def record(session, message_id, timestamp, role, content):
    return {
        "type": "message",
        "id": message_id,
        "timestamp": timestamp,
        "message": {"role": role, "content": content},
    }


def write_log(path, session, messages):
    rows = [{"type": "session", "id": session, "timestamp": messages[0]["timestamp"]}]
    rows.extend(messages)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


class ChatSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "sessions"
        self.root.mkdir()
        self.db = Path(self.temp.name) / "chat.db"
        self.log = self.root / "session-a.jsonl"
        self.first = record(
            "session-a", "message-1", "2026-01-01T01:00:00Z", "user", "yellow vanadinite"
        )
        write_log(self.log, "session-a", [self.first])

    def tearDown(self):
        self.temp.cleanup()

    def quiet(self, function, *args, **kwargs):
        with redirect_stdout(io.StringIO()):
            return function(*args, **kwargs)

    def test_initial_index_is_searchable_and_machine_described(self):
        receipt = self.quiet(chat_search.index, self.db, self.root, True)
        self.assertEqual(receipt["verification"]["messages"], 1)
        self.assertFalse(receipt["authoritative"])
        found = self.quiet(
            chat_search.search, self.db, "vanadinite", json_mode=True, root=self.root
        )
        self.assertEqual(found["result_count"], 1)
        self.assertEqual(found["index_status"]["freshness"], "current")
        self.assertEqual(found["results"][0]["evidence"][0]["source_file"], self.log.name)
        self.assertEqual(self.quiet(chat_search.status, self.db, self.root, False, True)["freshness"], "current")

    def test_oversized_search_fails_before_state_change(self):
        self.quiet(chat_search.index, self.db, self.root, True)
        with self.assertRaises(ValueError):
            self.quiet(chat_search.search, self.db, "vanadinite", 501)
        self.assertEqual(self.quiet(chat_search.stats, self.db, True)["messages"], 1)

    def test_incremental_update_preserves_prior_revision_and_deduplicates(self):
        self.quiet(chat_search.index, self.db, self.root, True)
        second = record(
            "session-a", "message-2", "2026-01-01T02:00:00Z", "assistant", "goethite coating"
        )
        time.sleep(0.002)
        write_log(self.log, "session-a", [self.first, second])
        self.assertEqual(self.quiet(chat_search.status, self.db, self.root, False, True)["freshness"], "stale")
        receipt = self.quiet(chat_search.index, self.db, self.root, True)
        self.assertEqual(receipt["messages_added"], 1)
        self.assertIsNotNone(receipt["preserved_previous_index"])
        stats = self.quiet(chat_search.stats, self.db, True)
        self.assertEqual(stats["messages"], 2)
        self.assertEqual(stats["source_revisions"], 2)
        no_op = self.quiet(chat_search.index, self.db, self.root, True)
        self.assertTrue(no_op["no_changes"])
        self.assertIsNone(no_op["preserved_previous_index"])

    def test_duplicate_message_in_two_files_has_two_evidence_pointers(self):
        duplicate = self.root / "session-a.jsonl.reset.copy"
        write_log(duplicate, "session-a", [self.first])
        self.quiet(chat_search.index, self.db, self.root, True)
        result = self.quiet(chat_search.search, self.db, "vanadinite", json_mode=True)["results"][0]
        self.assertEqual(len(result["evidence"]), 2)
        self.assertEqual(self.quiet(chat_search.stats, self.db, True)["messages"], 1)

    def test_duplicate_message_in_one_file_retains_each_line_pointer(self):
        write_log(self.log, "session-a", [self.first, self.first])
        self.quiet(chat_search.index, self.db, self.root, True)
        result = self.quiet(
            chat_search.search, self.db, "vanadinite", json_mode=True
        )["results"][0]
        self.assertEqual([item["source_line"] for item in result["evidence"]], [2, 3])

    def test_touch_is_reconciled_and_does_not_leave_permanent_staleness(self):
        self.quiet(chat_search.index, self.db, self.root, True)
        time.sleep(0.002)
        self.log.touch()
        self.assertEqual(
            self.quiet(chat_search.status, self.db, self.root, False, True)["freshness"],
            "stale",
        )
        receipt = self.quiet(chat_search.index, self.db, self.root, True)
        self.assertTrue(receipt["promoted"])
        self.assertEqual(
            self.quiet(chat_search.status, self.db, self.root, False, True)["freshness"],
            "current",
        )

    def test_verified_index_repairs_same_size_same_mtime_edit(self):
        self.quiet(chat_search.index, self.db, self.root, True)
        original = self.log.stat()
        text = self.log.read_text().replace("vanadinite", "vanadinitX")
        self.assertEqual(len(text), self.log.stat().st_size)
        self.log.write_text(text)
        os.utime(self.log, ns=(original.st_atime_ns, original.st_mtime_ns))
        self.assertEqual(
            self.quiet(chat_search.status, self.db, self.root, True, True)["freshness"],
            "stale",
        )
        receipt = self.quiet(chat_search.index, self.db, self.root, True, True)
        self.assertTrue(receipt["verified_sources"])
        result = self.quiet(
            chat_search.search, self.db, "vanadinitX", json_mode=True, root=self.root
        )
        self.assertEqual(result["result_count"], 1)

    def test_missing_source_is_reported_without_losing_message(self):
        self.quiet(chat_search.index, self.db, self.root, True)
        self.log.unlink()
        state = self.quiet(chat_search.status, self.db, self.root, False, True)
        self.assertEqual(state["sources"]["missing_but_retained"], 1)
        self.assertEqual(state["source_health"], "degraded")
        self.assertEqual(self.quiet(chat_search.search, self.db, "vanadinite", json_mode=True)["result_count"], 1)
        receipt = self.quiet(chat_search.index, self.db, self.root, True)
        self.assertEqual(receipt["verification"]["messages"], 1)

    def test_missing_corpus_root_does_not_make_retained_messages_unsearchable(self):
        self.quiet(chat_search.index, self.db, self.root, True)
        moved = self.root.with_name("sessions-moved")
        self.root.rename(moved)
        state = self.quiet(chat_search.status, self.db, self.root, False, True)
        self.assertEqual(state["freshness"], "unknown")
        self.assertEqual(state["source_health"], "unavailable")
        result = self.quiet(
            chat_search.search, self.db, "vanadinite", json_mode=True, root=self.root
        )
        self.assertEqual(result["result_count"], 1)

    def test_naive_timestamps_and_date_filters_are_utc(self):
        self.first["timestamp"] = "2026-01-01T01:00:00"
        write_log(self.log, "session-a", [self.first])
        self.quiet(chat_search.index, self.db, self.root, True)
        result = self.quiet(
            chat_search.search, self.db, "vanadinite", after="2026-01-01", json_mode=True
        )
        self.assertEqual(result["result_count"], 1)

    def test_undated_messages_are_counted_and_reported_separately(self):
        self.first["timestamp"] = ""
        write_log(self.log, "session-a", [self.first])
        self.quiet(chat_search.index, self.db, self.root, True)
        stats = self.quiet(chat_search.stats, self.db, True)
        state = self.quiet(chat_search.status, self.db, self.root, False, True)
        self.assertEqual(stats["messages"], 1)
        self.assertEqual(stats["undated_messages"], 1)
        self.assertEqual(state["coverage"]["messages"], 1)

    def test_json_main_converts_oserror_to_structured_error(self):
        with mock.patch.object(chat_search, "index", side_effect=PermissionError("denied")):
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = chat_search.main(["index", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stream.getvalue())["error"]["type"], "PermissionError")

    def test_failed_preservation_does_not_leave_counterfeit_backup(self):
        self.db.write_bytes(b"not sqlite")
        with self.assertRaises(sqlite3.DatabaseError):
            self.quiet(chat_search.index, self.db, self.root, True)
        self.assertEqual(list(self.db.parent.glob("chat.db.pre-index-*")), [])

    def test_nonempty_live_wal_sidecar_blocks_promotion(self):
        self.quiet(chat_search.index, self.db, self.root, True)
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("INSERT INTO meta VALUES('wal_probe','present')")
            conn.commit()
            second = self.root / "session-b.jsonl"
            write_log(second, "session-b", [self.first])
            with self.assertRaises(RuntimeError):
                self.quiet(chat_search.index, self.db, self.root, True)
        finally:
            conn.close()
        self.assertEqual(
            self.quiet(chat_search.search, self.db, "vanadinite", json_mode=True)[
                "result_count"
            ],
            1,
        )
        self.assertEqual(list(self.db.parent.glob("chat.db.pre-index-*")), [])

    def test_discovery_includes_jsonl_zst_and_excludes_migration_metadata(self):
        compressed = self.root / "live.jsonl.zst"
        migrated = self.root / "old.jsonl.deleted.1.codex-app-server.json.migrated"
        compressed.touch()
        migrated.touch()
        names = {path.name for path in chat_search.candidates(self.root)}
        self.assertIn(compressed.name, names)
        self.assertNotIn(migrated.name, names)

    @unittest.skipUnless(chat_search.shutil.which("zstd"), "zstd unavailable")
    def test_corrupt_changed_archive_does_not_replace_live_database(self):
        compressed = self.root / "session-z.jsonl.deleted.test.zst"
        plain = Path(self.temp.name) / "source.jsonl"
        write_log(plain, "session-z", [self.first])
        subprocess.run(["zstd", "-q", "-f", str(plain), "-o", str(compressed)], check=True)
        self.quiet(chat_search.index, self.db, self.root, True)
        searchable_before = self.quiet(chat_search.search, self.db, "vanadinite", json_mode=True)
        compressed.write_bytes(b"not zstd")
        with self.assertRaises(RuntimeError):
            self.quiet(chat_search.index, self.db, self.root, True)
        searchable_after = self.quiet(chat_search.search, self.db, "vanadinite", json_mode=True)
        self.assertEqual(searchable_before["result_count"], searchable_after["result_count"])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
