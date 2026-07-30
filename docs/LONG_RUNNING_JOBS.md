# LONG_RUNNING_JOBS.md

**Operational runbook for jobs that outlive a chat session.** Read this
before starting or recovering any multi-hour/multi-day collection job.
For current execution state see `PROJECT_STATE.md`; this document is
procedure only, not status.

## Why this exists

The Backlog 1.5 liquidation backfill was launched as a child of an
interactive session. When that session ended, the job died with it after
49 of 367 days — leaving an **empty** output file: no completion line, no
failure line, no traceback. Nothing was corrupted and nothing had to be
re-derived (the checkpoint's durability guarantees held exactly as
designed, and re-running resumed from the right place), but roughly nine
hours of wall-clock transfer had to be repeated.

The defect was never in the pipeline. It was that a job's **lifetime was
coupled to a chat session's lifetime**. This runbook and the three
scripts it describes decouple them.

## The three tools

All live in `scripts/`, are stdlib-only, and change **nothing** about the
collection pipeline, storage, checkpoint semantics, or research logic.
Two of the three are strictly read-only.

| Script | Role | Writes anything? |
|---|---|---|
| `run_detached_job.py` | Starts a command detached from the calling shell | Only job metadata (`pid`/`cmd`/`started`/`log`) |
| `job_status.py` | Inspect / follow a job; the "reattach" path | **No — read-only** |
| `liquidation_backfill_progress.py` | Backfill progress + data sanity from on-disk state | **No — read-only** |

Because the latter two never write, signal, or lock anything, they are
safe to run at any time — including mid-flight, from several sessions at
once, while you work on something else entirely.

## Starting a long-running job

```bash
python scripts/run_detached_job.py --name liq_backfill -- \
    python -m alpha_engine.historical.backfill_liquidations \
        --symbols BTC ETH SOL --start 2025-07-27 --end 2026-07-28
```

The job now has no controlling terminal and no dependency on the shell,
the chat session, or the browser. State lands in
`data/runtime/jobs/<name>/` (gitignored, like everything under `data/`).

Starting the same `--name` twice while it is running is **refused**. This
is deliberate and important: two backfills writing the same CSVs
concurrently is the one genuinely dangerous mistake in this workflow —
`storage.merge_and_write` is read-modify-write with no inter-process
lock, so two writers silently lose one writer's rows.

**How the guard decides (it fails closed):**

| What it finds | Decision |
|---|---|
| Recorded pid alive **and** its command line matches the recorded `cmd` | **Refuse** — the job really is running |
| Recorded pid alive but a **different** process (OS recycled the pid) | Start — the job is genuinely gone |
| Recorded pid definitively gone | Start |
| **Cannot tell** (process probe failed/timed out) | **Refuse** — see below |

The last row matters: if the machine is too loaded or locked-down for the
probe to answer, the guard refuses rather than gambling. It will tell you
exactly which pid it could not verify. Re-run once the machine is
responsive; only if you have confirmed by hand that the pid is truly gone
should you delete the job's `pid` file to unblock it.

A `lock` file makes claiming a job atomic, so two near-simultaneous
starts (two shells, two Claude sessions) cannot both slip through. A lock
left by a job that has since exited is reclaimed automatically — but only
when its holder is *provably* gone, never when liveness is merely
unverifiable.

## Checking on it — from any session, any time

```bash
python scripts/job_status.py                      # list every known job
python scripts/job_status.py liq_backfill         # status + recent log
python scripts/job_status.py liq_backfill --follow # stream new output
python scripts/liquidation_backfill_progress.py    # % complete + data sanity
```

**You never reattach to the process** — a detached job has no terminal by
design. You reattach to its *observable state*: pid, append-only log, and
(for collection jobs) the pipeline's own durable checkpoint. All three
survive a chat disconnect, a terminal close, a browser close, and a
reboot.

For the liquidation backfill specifically, the CLI prints only at the
very end, so an empty log mid-run is normal — **use the checkpoint, not
the log, to judge progress.**

`job_status.py`'s `RUNNING` verdict is a *display* check: it asks only
whether some process holds that pid, and on a probe failure it renders
`NOT RUNNING`. It is deliberately not the authority on whether starting
is safe — `run_detached_job.py` applies the stricter identity-and-
fail-closed logic above for that. So when it matters, confirm progress
with `liquidation_backfill_progress.py` (a checkpoint that is not
advancing is the real signal), not with the `RUNNING` label alone.

## Recovering after any interruption

Interruption means chat disconnect, internet drop, laptop sleep/reboot,
crash, or manual kill. The procedure is the same for all of them.

1. **Check whether it is actually still running.**
   ```bash
   python scripts/job_status.py liq_backfill
   ```
   If `RUNNING`: **do nothing.** Do not restart it. Detached jobs commonly
   survive things that kill the chat.

2. **If `NOT RUNNING`, determine how it ended** — look at the log tail in
   that same output:
   - `BACKFILL_COMPLETE` → finished; nothing to do.
   - `BACKFILL_FAILED` → exhausted its retries; the message says why.
   - **Neither** → killed externally (session teardown, reboot, `taskkill`).
     This is the common case and is not a data problem.

3. **Confirm what survived** before touching anything:
   ```bash
   python scripts/liquidation_backfill_progress.py
   ```
   Expect `rows/event = 2.00` on every symbol and contiguous day runs.

4. **Resume by re-running the identical command.** The pipeline skips
   everything at or before the checkpoint and continues from the next
   unprocessed hour.

**Never do these to "recover":**
- ❌ `--force` — that reprocesses the whole range from scratch. It exists
  to *re-verify* data, not to recover from an interruption.
- ❌ Deleting or hand-editing the checkpoint or any collected CSV.
- ❌ Starting a second copy alongside a running one.

At most one *partial* day is ever discarded on interruption, and that is
by design: the checkpoint only advances after that day's rows are durably
flushed, so an interrupted day is retried whole rather than left
half-persisted. Losing a partial day costs a re-download; a checkpoint
that ran ahead of the data would cost silent, permanent data loss. The
pipeline deliberately chooses the former (see `PROJECT_STATE.md`, the
Backlog 1.3 QA cycle's H1 finding).

## Surviving a reboot

Nothing auto-restarts on boot today, and nothing needs to: the checkpoint
makes restart-after-reboot cheap and safe. After a reboot, run step 1
above; if it is not running, re-run the same command. Progress resumes
from the last durable checkpoint rather than from the beginning.

Registering the job with the OS scheduler (Task Scheduler / systemd /
cron) would remove even that manual step. It is deliberately **not** done
here — that is deployment configuration, and the project has no present
need for unattended restart of a research backfill (Constitution §5:
nothing is built ahead of a concrete, present need). The scripts are
scheduler-agnostic, so if that need appears, any scheduler can invoke the
exact same command.

## Working on other things while a job runs

Nothing special is required. The job is fully independent — start it,
then use the repository normally in the same or any other session. Only
two rules apply:

1. Don't start a second copy of the same job (the tool refuses anyway).
2. Treat the collected series as append-only while a job is writing to
   it — read them freely, but don't hand-edit them mid-run.
