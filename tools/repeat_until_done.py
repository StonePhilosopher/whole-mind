#!/usr/bin/env python3
"""Durable repeat-until-done tasks for agent workspaces.

The scheduler is deliberately outside this tool. A cron service, heartbeat, or
agent automation wakes the task once. The task is then either completed or
given one new wake time. This module keeps the durable identity, lease, retry
policy, and history that make those one-shot wakes safe across restarts.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCHEMA_VERSION = 1
DURATION_RE = re.compile(r"^(?P<amount>[1-9][0-9]*)(?P<unit>[smhdw])$")
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_duration(value: str) -> int:
    match = DURATION_RE.fullmatch(value.strip().lower())
    if not match:
        raise ValueError("duration must look like 30m, 12h, 3d, or 2w")
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    return int(match.group("amount")) * multipliers[match.group("unit")]


def parse_time(value: str, now: datetime | None = None) -> datetime:
    value = value.strip()
    now = now or utc_now()
    if value == "now":
        return now
    if value.startswith("+"):
        return now + timedelta(seconds=parse_duration(value[1:]))
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("absolute times must include a UTC offset or Z")
    return parsed.astimezone(timezone.utc)


def default_state_path() -> Path:
    configured = os.environ.get("WHOLE_MIND_REPEAT_STATE")
    if configured:
        return Path(configured).expanduser().resolve()
    workspace = Path(__file__).resolve().parent.parent
    return workspace / "memory" / "repeat-until-done.json"


def read_state(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "tasks": {}}
    with path.open(encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported state schema: {state.get('schema_version')}")
    if not isinstance(state.get("tasks"), dict):
        raise ValueError("state file has no task map")
    return state


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class LockedState:
    def __init__(self, path: Path):
        self.path = path
        self.lock = None
        self.state = None

    def __enter__(self) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = self.path.with_suffix(self.path.suffix + ".lock").open("a+b")
        if os.name == "nt":
            import msvcrt

            self.lock.seek(0)
            if self.lock.read(1) == b"":
                self.lock.seek(0)
                self.lock.write(b"0")
                self.lock.flush()
            self.lock.seek(0)
            msvcrt.locking(self.lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX)
        self.state = read_state(self.path)
        return self.state

    def __exit__(self, error_type, error, traceback) -> None:
        try:
            if error_type is None:
                write_state(self.path, self.state)
        finally:
            if os.name == "nt":
                import msvcrt

                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.lock.fileno(), fcntl.LOCK_UN)
            self.lock.close()


def event(task: dict, kind: str, now: datetime, note: str | None = None, **extra) -> None:
    entry = {"at": iso(now), "event": kind}
    if note:
        entry["note"] = note
    entry.update(extra)
    task.setdefault("history", []).append(entry)


def recover_expired_claims(state: dict, now: datetime) -> int:
    recovered = 0
    for task in state["tasks"].values():
        if task["status"] != "claimed" or not task.get("lease_expires_at"):
            continue
        if parse_time(task["lease_expires_at"]) > now:
            continue
        task["status"] = "scheduled"
        task["next_run_at"] = iso(now)
        task["lease_expires_at"] = None
        event(task, "lease_expired", now)
        recovered += 1
    return recovered


def retry_delay(task: dict) -> int:
    base = task["retry"]["seconds"]
    if task["retry"]["strategy"] == "fixed":
        return base
    exponent = max(task["attempts"] - 1, 0)
    maximum = task["retry"].get("max_seconds") or base * 32
    return min(base * (2**exponent), maximum)


def generated_id(text: str) -> str:
    slug = "-".join(re.findall(r"[a-z0-9]+", text.lower())[:5]) or "task"
    return f"{slug}-{uuid.uuid4().hex[:8]}"


def validate_id(identifier: str) -> str:
    if not TASK_ID_RE.fullmatch(identifier):
        raise ValueError("task id may contain only letters, numbers, dot, underscore, and hyphen")
    return identifier


def scheduler_prompt(task: dict, path: Path) -> str:
    state_option = f"--state {shlex.quote(str(path))} "
    tool = shlex.quote(str(Path(__file__).resolve()))
    command = f"python3 {tool} {state_option}"
    return f"""WHOLE MIND REPEAT-UNTIL-DONE WAKE

Task id: {task['id']}
Task: {task['task']}
Completion evidence: {task['completion']}

1. Claim this exact task before acting:
   {command}claim {task['id']}
2. Inspect the real completion evidence. Do not infer completion from memory or elapsed time.
3. If complete, record the evidence and stop:
   {command}resolve {task['id']} done --note \"<evidence>\"
4. If incomplete, record why:
   {command}resolve {task['id']} retry --note \"<reason>\"
5. A retry returns next_run_at. Create exactly one new one-shot wake at that time with this same prompt. Create no new wake after done or escalated."""


def require_task(state: dict, identifier: str) -> dict:
    validate_id(identifier)
    try:
        return state["tasks"][identifier]
    except KeyError as error:
        raise ValueError(f"unknown task: {identifier}") from error


def clone(value):
    return json.loads(json.dumps(value))


def cmd_add(args, path: Path, now: datetime) -> dict:
    first = parse_time(args.at, now)
    identifier = validate_id(args.id or generated_id(args.task))
    if args.max_attempts < 0:
        raise ValueError("max attempts cannot be negative")
    retry_seconds = parse_duration(args.retry)
    max_retry_seconds = parse_duration(args.max_retry) if args.max_retry else None
    if max_retry_seconds is not None and max_retry_seconds < retry_seconds:
        raise ValueError("maximum retry delay cannot be shorter than the base retry delay")
    with LockedState(path) as state:
        if identifier in state["tasks"]:
            raise ValueError(f"task already exists: {identifier}")
        task = {
            "id": identifier,
            "task": args.task,
            "completion": args.complete_when,
            "status": "scheduled",
            "created_at": iso(now),
            "next_run_at": iso(first),
            "attempts": 0,
            "max_attempts": args.max_attempts or None,
            "lease_seconds": parse_duration(args.lease),
            "lease_expires_at": None,
            "retry": {
                "seconds": retry_seconds,
                "strategy": args.backoff,
                "max_seconds": max_retry_seconds,
            },
            "completed_at": None,
            "history": [],
        }
        event(task, "created", now, next_run_at=task["next_run_at"])
        state["tasks"][identifier] = task
    result = clone(task)
    result["scheduler_prompt"] = scheduler_prompt(task, path)
    return result


def cmd_due(args, path: Path, now: datetime) -> dict:
    with LockedState(path) as state:
        recovered = recover_expired_claims(state, now)
        tasks = [
            clone(task)
            for task in state["tasks"].values()
            if task["status"] == "scheduled" and parse_time(task["next_run_at"]) <= now
        ]
    tasks.sort(key=lambda item: (item["next_run_at"], item["id"]))
    return {"as_of": iso(now), "recovered_expired_claims": recovered, "tasks": tasks}


def cmd_claim(args, path: Path, now: datetime) -> dict:
    with LockedState(path) as state:
        recover_expired_claims(state, now)
        task = require_task(state, args.id)
        if task["status"] != "scheduled":
            raise ValueError(f"task is {task['status']}, not scheduled")
        if parse_time(task["next_run_at"]) > now:
            raise ValueError(f"task is not due until {task['next_run_at']}")
        task["status"] = "claimed"
        task["attempts"] += 1
        task["lease_expires_at"] = iso(now + timedelta(seconds=task["lease_seconds"]))
        event(task, "claimed", now, attempt=task["attempts"], lease_expires_at=task["lease_expires_at"])
        return clone(task)


def cmd_resolve(args, path: Path, now: datetime) -> dict:
    with LockedState(path) as state:
        task = require_task(state, args.id)
        if task["status"] != "claimed":
            raise ValueError(f"task is {task['status']}, not claimed")
        task["lease_expires_at"] = None
        if args.outcome == "done":
            task["status"] = "completed"
            task["completed_at"] = iso(now)
            task["next_run_at"] = None
            event(task, "completed", now, args.note)
        elif task["max_attempts"] is not None and task["attempts"] >= task["max_attempts"]:
            task["status"] = "escalated"
            task["next_run_at"] = None
            event(task, "escalated", now, args.note)
        else:
            delay = retry_delay(task)
            task["status"] = "scheduled"
            task["next_run_at"] = iso(now + timedelta(seconds=delay))
            event(task, "rescheduled", now, args.note, delay_seconds=delay, next_run_at=task["next_run_at"])
        return clone(task)


def cmd_cancel(args, path: Path, now: datetime) -> dict:
    with LockedState(path) as state:
        task = require_task(state, args.id)
        if task["status"] in {"completed", "cancelled"}:
            raise ValueError(f"task is already {task['status']}")
        task["status"] = "cancelled"
        task["next_run_at"] = None
        task["lease_expires_at"] = None
        event(task, "cancelled", now, args.note)
        return clone(task)


def cmd_show(args, path: Path, now: datetime) -> dict:
    return clone(require_task(read_state(path), args.id))


def cmd_list(args, path: Path, now: datetime) -> dict:
    tasks = list(read_state(path)["tasks"].values())
    if args.status:
        tasks = [task for task in tasks if task["status"] == args.status]
    tasks.sort(key=lambda item: (item.get("next_run_at") or "~", item["id"]))
    return {"tasks": [clone(task) for task in tasks]}


def cmd_prompt(args, path: Path, now: datetime) -> dict:
    task = require_task(read_state(path), args.id)
    return {"id": task["id"], "next_run_at": task["next_run_at"], "prompt": scheduler_prompt(task, path)}


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--state", type=Path, default=default_state_path())
    root.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    commands = root.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="create a durable one-shot task")
    add.add_argument("--id")
    add.add_argument("--task", required=True)
    add.add_argument("--complete-when", required=True, help="observable completion evidence")
    add.add_argument("--at", default="now", help="ISO-8601 time or a relative value such as +2h")
    add.add_argument("--retry", default="1d")
    add.add_argument("--backoff", choices=("fixed", "exponential"), default="fixed")
    add.add_argument("--max-retry", help="cap for exponential backoff")
    add.add_argument("--max-attempts", type=int, default=0, help="0 means no automatic escalation")
    add.add_argument("--lease", default="1h")

    commands.add_parser("due", help="list due tasks and recover expired claims")
    claim = commands.add_parser("claim", help="lease a due task before doing work")
    claim.add_argument("id")
    resolve = commands.add_parser("resolve", help="complete or reschedule a claimed task")
    resolve.add_argument("id")
    resolve.add_argument("outcome", choices=("done", "retry"))
    resolve.add_argument("--note", required=True, help="completion evidence or retry reason")
    cancel = commands.add_parser("cancel", help="cancel a nonterminal task")
    cancel.add_argument("id")
    cancel.add_argument("--note", required=True)
    show = commands.add_parser("show", help="show one task")
    show.add_argument("id")
    listing = commands.add_parser("list", help="list tasks")
    listing.add_argument("--status", choices=("scheduled", "claimed", "completed", "escalated", "cancelled"))
    prompt = commands.add_parser("prompt", help="print the portable scheduler prompt")
    prompt.add_argument("id")
    return root


def render(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif "scheduler_prompt" in result:
        print(f"Created {result['id']} — first wake {result['next_run_at']}")
        print("\n" + result["scheduler_prompt"])
    elif "prompt" in result:
        print(result["prompt"])
    elif "tasks" in result:
        if not result["tasks"]:
            print("No matching tasks.")
        for task in result["tasks"]:
            print(f"{task['id']}\t{task['status']}\t{task.get('next_run_at') or '-'}\t{task['task']}")
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


def main(argv=None, *, now: datetime | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = args.state.expanduser().resolve()
    handlers = {
        "add": cmd_add,
        "due": cmd_due,
        "claim": cmd_claim,
        "resolve": cmd_resolve,
        "cancel": cmd_cancel,
        "show": cmd_show,
        "list": cmd_list,
        "prompt": cmd_prompt,
    }
    try:
        result = handlers[args.command](args, path, now or utc_now())
        render(result, args.json)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        if args.json:
            print(json.dumps({"error": {"type": type(error).__name__, "message": str(error)}}))
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
