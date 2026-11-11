import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools/repeat_until_done.py"
SPEC = importlib.util.spec_from_file_location("repeat_until_done", MODULE_PATH)
repeat_until_done = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repeat_until_done)


class RepeatUntilDoneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name) / "state.json"
        self.now = datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *arguments, now=None):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = repeat_until_done.main(
                ["--state", str(self.state), "--json", *arguments], now=now or self.now
            )
        return code, json.loads(stream.getvalue())

    def add(self, **overrides):
        arguments = [
            "add", "--id", overrides.get("id", "review-pr"),
            "--task", "Review PR", "--complete-when", "A durable review receipt exists",
            "--at", overrides.get("at", "now"), "--retry", overrides.get("retry", "1d"),
        ]
        if overrides.get("backoff"):
            arguments += ["--backoff", overrides["backoff"]]
        if overrides.get("max_attempts"):
            arguments += ["--max-attempts", str(overrides["max_attempts"])]
        code, result = self.run_cli(*arguments)
        self.assertEqual(code, 0, result)
        return result

    def test_add_writes_durable_task_and_scheduler_contract(self):
        result = self.add()
        self.assertEqual(result["status"], "scheduled")
        self.assertEqual(result["next_run_at"], "2026-11-11T15:00:00Z")
        self.assertIn("exactly one new one-shot wake", result["scheduler_prompt"])
        saved = json.loads(self.state.read_text())
        self.assertEqual(saved["tasks"]["review-pr"]["completion"], "A durable review receipt exists")

    def test_early_claim_is_refused_without_incrementing_attempts(self):
        self.add(at="+1h")
        code, error = self.run_cli("claim", "review-pr")
        self.assertEqual(code, 1)
        self.assertIn("not due", error["error"]["message"])
        self.assertEqual(json.loads(self.state.read_text())["tasks"]["review-pr"]["attempts"], 0)

    def test_claim_then_complete_is_terminal(self):
        self.add()
        code, claimed = self.run_cli("claim", "review-pr")
        self.assertEqual(code, 0)
        self.assertEqual(claimed["attempts"], 1)
        code, completed = self.run_cli("resolve", "review-pr", "done", "--note", "receipt abc123")
        self.assertEqual(code, 0)
        self.assertEqual(completed["status"], "completed")
        self.assertIsNone(completed["next_run_at"])
        _, due = self.run_cli("due", now=self.now + timedelta(days=10))
        self.assertEqual(due["tasks"], [])

    def test_incomplete_task_gets_one_new_fixed_wake(self):
        self.add(retry="2d")
        self.run_cli("claim", "review-pr")
        later = self.now + timedelta(minutes=10)
        code, retried = self.run_cli(
            "resolve", "review-pr", "retry", "--note", "builder has not pushed", now=later
        )
        self.assertEqual(code, 0)
        self.assertEqual(retried["next_run_at"], "2026-11-13T15:10:00Z")

    def test_exponential_backoff_uses_attempt_number(self):
        self.add(retry="1h", backoff="exponential")
        self.run_cli("claim", "review-pr")
        _, first = self.run_cli("resolve", "review-pr", "retry", "--note", "not yet")
        first_wake = repeat_until_done.parse_time(first["next_run_at"])
        self.run_cli("claim", "review-pr", now=first_wake)
        _, second = self.run_cli(
            "resolve", "review-pr", "retry", "--note", "still not", now=first_wake
        )
        self.assertEqual(repeat_until_done.parse_time(second["next_run_at"]) - first_wake, timedelta(hours=2))

    def test_max_attempts_escalates_instead_of_rescheduling(self):
        self.add(max_attempts=1)
        self.run_cli("claim", "review-pr")
        _, result = self.run_cli("resolve", "review-pr", "retry", "--note", "needs a human")
        self.assertEqual(result["status"], "escalated")
        self.assertIsNone(result["next_run_at"])

    def test_duplicate_claim_is_refused(self):
        self.add()
        self.run_cli("claim", "review-pr")
        code, error = self.run_cli("claim", "review-pr")
        self.assertEqual(code, 1)
        self.assertIn("claimed", error["error"]["message"])

    def test_expired_lease_is_recovered_by_due_scan(self):
        self.add()
        _, claimed = self.run_cli("claim", "review-pr")
        after_lease = repeat_until_done.parse_time(claimed["lease_expires_at"]) + timedelta(seconds=1)
        _, due = self.run_cli("due", now=after_lease)
        self.assertEqual(due["recovered_expired_claims"], 1)
        self.assertEqual([task["id"] for task in due["tasks"]], ["review-pr"])
        _, reclaimed = self.run_cli("claim", "review-pr", now=after_lease)
        self.assertEqual(reclaimed["attempts"], 2)

    def test_completion_requires_claim(self):
        self.add()
        code, error = self.run_cli("resolve", "review-pr", "done", "--note", "guess")
        self.assertEqual(code, 1)
        self.assertIn("not claimed", error["error"]["message"])

    def test_invalid_naive_time_is_rejected(self):
        code, error = self.run_cli(
            "add", "--task", "x", "--complete-when", "y", "--at", "2026-11-12T10:00:00"
        )
        self.assertEqual(code, 1)
        self.assertIn("UTC offset", error["error"]["message"])

    def test_unsafe_task_id_is_rejected_before_it_reaches_scheduler_prompt(self):
        code, error = self.run_cli(
            "add", "--id", "bad;touch", "--task", "x", "--complete-when", "y"
        )
        self.assertEqual(code, 1)
        self.assertIn("task id", error["error"]["message"])

    def test_retry_cap_cannot_be_shorter_than_base_delay(self):
        code, error = self.run_cli(
            "add", "--task", "x", "--complete-when", "y",
            "--retry", "2h", "--max-retry", "1h",
        )
        self.assertEqual(code, 1)
        self.assertIn("shorter", error["error"]["message"])


if __name__ == "__main__":
    unittest.main()
