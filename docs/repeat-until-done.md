# Repeat Until Done

A reminder says, “look at this later.” A durable obligation says, “keep coming
back until there is evidence that this is finished.” Whole Mind's
`repeat_until_done.py` turns a series of one-shot scheduler wakes into the
second kind.

The tool is framework-agnostic. It does not create cron jobs itself. It stores
the task's identity, observable completion condition, retry policy, lease, and
history. The surrounding agent framework supplies one wake at a time.

## Why one-shots instead of permanent cron

A permanent cron keeps firing after success unless something removes it. A
self-renewing one-shot has the opposite default: success ends the chain, while
an unfinished check creates exactly one later wake. Durable claims prevent two
wakes from doing the same work, and expired claims can be recovered after a
crash.

## Install

The Whole Mind scaffold copies the tool into `tools/`. Its default state file
is `memory/repeat-until-done.json`. Override it with `--state PATH` or the
`WHOLE_MIND_REPEAT_STATE` environment variable.

## Create a task

```bash
python3 tools/repeat_until_done.py add \
  --id review-pr-23 \
  --task "Review PR #23 at its exact head" \
  --complete-when "A durable review receipt exists for the current head" \
  --at +1d --retry 1d --max-attempts 3
```

The command prints a scheduler-ready prompt. Put that prompt in a one-shot job
at the returned `next_run_at`.

## At each wake

```bash
# Lease the task before making external changes
python3 tools/repeat_until_done.py claim review-pr-23

# Terminal success: include observable evidence
python3 tools/repeat_until_done.py resolve review-pr-23 done \
  --note "Approved exact head 87d4e9ab; review receipt 12345"

# Or: still incomplete. This returns next_run_at.
python3 tools/repeat_until_done.py resolve review-pr-23 retry \
  --note "Head changed after review; fresh verification required"
```

After `retry`, create exactly one new one-shot automation at `next_run_at` with
the same prompt. After `done` or `escalated`, create none.

## Inspect and recover

```bash
python3 tools/repeat_until_done.py due
python3 tools/repeat_until_done.py list --status scheduled
python3 tools/repeat_until_done.py show review-pr-23
python3 tools/repeat_until_done.py prompt review-pr-23
```

`due` also recovers claims whose leases expired after a crash. Every mutation
is written atomically under a lock, and every transition remains in the task's
history.

## Completion predicates

The `--complete-when` text should name evidence another fresh session can
inspect. Good predicates include:

- a PR is merged at an independently verified head;
- a file or database row contains a receipt;
- a TODO checkbox is marked complete with a date;
- a message has a durable delivery receipt;
- an external status endpoint reports the required state.

“I probably did it” and “enough time has passed” are not completion evidence.

## Safety boundary

The tool never executes arbitrary predicate commands. The agent checks the
evidence using its normal, scoped tools. This keeps a portable task file from
becoming a shell-execution mechanism.
