# Hostel transfer recovery

Transfers use durable checkpoints, authenticated router preflight and repeatable
failure recovery. PIN/admin authentication, profile comparisons, destination network
bindings and remaining-byte/uptime calculations protect the account throughout a move.

## What is persisted

Migration `20261008_0015` (after `20261008_0014`) adds
`hostel_transfer_operations`: operation/customer/router IDs, original router user ID,
destination user ID once confirmed, status/stage, remaining allowances, active
subscription IDs, last observed state, retry count/backoff, safe error code, actor
and timestamps. A partial unique index permits only one active operation per customer.

Only recovery-essential RouterOS settings and counters are saved in the snapshot.
Necessary Hotspot credentials are inside a Fernet authenticated envelope bound to the
operation ID. Its key is derived with a separate HKDF context from the existing
`PIN_HASH_SECRET`; request PINs and admin passwords are never journaled. Observations,
CLI output, audit records and recovery logs contain no credentials or raw router errors.
Encrypted snapshots are erased when operations complete or roll back.

## Safe progress and recovery

Each new move verifies **both router APIs** through their configured host/port and
the same authenticated connections used for the transfer. The checks read router
identity and the Hotspot menus, then run a harmless synchronous `/execute as-string`
probe. A cached `offline` status or ping result does not decide availability. Both
routers are checked even if the first probe fails. Recovery repeats these checks
before resuming writes.

Preflight failures do not disable users, clear sessions, create copies or create an
active transfer operation. The response identifies the source/destination and separates
connection, login, permission, unsupported command and catalogue configuration errors.
Storage/migration or encryption configuration failures have their own codes and are
not reported as router outages. After a durable transfer starts, uncertain outcomes
continue to return `hostel_transfer_unconfirmed` and retain the existing recovery path.
The operator journal records only fixed failure codes; raw API errors are never exposed.

The synchronous execution behavior is documented in the
[RouterOS scripting manual](https://manual.mikrotik.com/docs/developer-guides/scripting/).
Read-only probes establish API access and command support; write permissions are still
enforced by RouterOS when the guarded account mutations run.

The initial snapshot commits **before any router write**. Each mutation has a committed
intent. The source receives a unique operation marker and is temporarily disabled,
then its sessions/cookies are removed and usage is settled. This stops reconnects
while recovery is pending. The destination is created disabled with its own operation
marker and the existing remaining allowance, then verified. The source is removed,
customer/active-subscription router ownership commits, and the sole destination
regains its original comment and disabled setting.

Only the destination's original comment is restored, including its original `login=`
timestamp. Subscription dates, transaction records and activation records are never
rewritten. Exhausted finite data still uses the existing one-byte guard plus disabled
state; exhausted uptime retains the existing one-second guard plus disabled state.

All changes/removals of existing users run through synchronous RouterOS conditional
scripts. They check the confirmed item ID, username and current configurable settings
on the router before the write. Removal also checks observed counters. Script literals
are byte-escaped, so credentials/comments cannot inject commands. There is no fallback
to cleanup by username alone. Creation uses RouterOS's unique username plus the
operation marker to identify a copy after a lost reply.

If a router fails while the original source still exists, recovery normally rolls back:
it verifies both routers, removes only an unchanged disabled destination, then restores
the source's original flags/comment **without writing its limits or counters**. Thus
1000 purchased bytes minus 400 used bytes remains 600 available after rollback.
If source removal succeeded, recovery finishes the destination and database instead
of recreating the source or crediting another allowance. Lost commit acknowledgements
are resolved by reading persisted ownership, never by trusting an in-memory object.

A dedicated PostgreSQL session advisory lock covers all checkpoints and router writes,
across HTTP requests, workers and operator retries. Customer rows and active
subscriptions are re-locked for the ownership commit. The active-operation index also
blocks a new transfer while recovery is outstanding. Account deletion/retention uses
the same lock and refuses to erase a pending recovery journal.

## Automatic reconciliation

The existing FastAPI lifespan starts a recovery task after 15 seconds, then polls every
60 seconds by default. It processes up to 50 due operations per pass, taking the same
customer lock and inspecting both routers. Failures retry with exponential backoff
from 60 seconds to one hour. Unfinished durable intents survive backend restarts even
when saving the latest failure was impossible during a database outage.

Settings:

```dotenv
HOSTEL_TRANSFER_RECOVERY_ENABLED=true
HOSTEL_TRANSFER_RECOVERY_INTERVAL_SECONDS=60
```

No queue or external scheduler is needed. All backend processes must use the same
database and `PIN_HASH_SECRET`. PostgreSQL connections must support session-level
advisory locks; use direct connections or session pooling, rather than transaction
pooling. The lock holds an additional connection per running transfer.

## Operator inspection and retry

From `backend/`, list unfinished operations:

```bash
python -m app.commands.recover_hostel_transfers
```

Output includes operation ID, customer/router IDs, status, stage, reason, attempts and
next retry time. `manual_review` operations are excluded from automatic retries.
After investigating the named operation and its router accounts:

```bash
python -m app.commands.recover_hostel_transfers --reconcile --operation-id UUID
python -m app.commands.recover_hostel_transfers --reconcile --operation-id UUID --retry-manual
```

An explicit ID bypasses backoff; `--retry-manual` rechecks a specific manual case.
Neither option bypasses ownership/settings checks, changes quotas or force-deletes users.
Running `--reconcile` without an ID retries the currently due non-manual operations.
The command uses the configured deployment database and routers; execute it only in
the intended environment.

Manual reason codes cover changed/replaced users, unexpected destination settings,
usage on a staged destination, changed source usage after settlement, missing accounts,
changed customer/subscription ownership and damaged/unreadable snapshots. Keep the
original encryption key and correct independently verified router state before retrying.

## Cases requiring intervention

Recovery waits while routers or PostgreSQL remain unreachable; accounts can remain
disabled during this period. Arbitrary router edits, newly purchased/replaced plans,
usage on a supposedly disabled copy, deletion of the only remaining account, both
accounts disappearing, or loss of the snapshot/key cannot be corrected automatically
without guessing ownership or allowance. Those cases retain the journal and require
operator investigation. An operation is never automatically abandoned and a second
transfer is blocked until it is resolved.

RouterOS scripts are checked conditional mutations, not a distributed transaction.
Other tools/router scripts must not concurrently edit a transfer-owned user; detectable
interference goes to manual review. Recovery preserves existing comments, so profile
scripts that legitimately rewrite comments during the final enable can also require
review. Normal existing `login=` timestamps are preserved.

Transfers already interrupted by older code have no journal and need independent
investigation. The new worker cannot reconstruct missing historical allowances.

## Installation and validation

Install the updated backend dependencies, including `cryptography>=46.0.0`. Resolve
any older in-flight transfer before changing versions, stop old backend processes,
apply `alembic upgrade head`, then start only the updated workers. Alembic is not
run automatically. Keep a backed-up, high-entropy `PIN_HASH_SECRET` (at least 32
characters) identical across workers; finish pending transfers before rotating it.
Validate synchronous `/execute as-string` and Hotspot mutation permissions in a
non-production RouterOS environment before rollout. No live-router validation was
performed for this implementation.

The migration was tested against an isolated local PostgreSQL instance. Downgrade
refuses to drop the table while any operation is active; resolve those operations first.
It requires an online connection for this guard, so offline downgrade SQL is unsupported.

Automated coverage includes checkpoints before/after commits, process death after router
writes, lost creation/deletion/commit replies, sustained database outage, unreachable
routers during rollback/cleanup, safe manual review, exhausted allowance, unchanged
subscription dates, repeated retries, encrypted snapshots, background reconciliation,
concurrent requests and cross-process PostgreSQL locking.

Run the backend suite with `python -m pytest -q`. Optional PostgreSQL tests require a
dedicated local database, never the deployment `DATABASE_URL`:

```dotenv
HOSTEL_TRANSFER_TEST_DATABASE_URL=postgresql+psycopg://transfer_test@127.0.0.1:55439/hostel_transfer_recovery_test
```

These tests create/drop only UUID-named private schemas. Without that variable the
three PostgreSQL integration tests skip. SQLite tests are isolated and use local
thread locks; SQLite is not supported for production cross-process recovery.

Validation on 2026-10-08: **255 backend tests passed**, including all three PostgreSQL
integration tests against a temporary local PostgreSQL 18 cluster. Ruff checks on
every changed Python file and `git diff --check` passed. The suite reported one
existing Starlette/httpx deprecation warning. No production database/router was used,
and the temporary cluster was stopped after testing.

## Files

New: `app/models/hostel_transfer.py`, `app/core/transfer_security.py`,
`app/integrations/mikrotik/transfer.py`, `app/services/transfer_lock.py`,
`app/services/hostel_transfer_recovery.py`,
`app/services/hostel_transfer_reconciliation.py`,
`app/commands/recover_hostel_transfers.py`,
`alembic/versions/20261008_0015_hostel_transfer_recovery.py`,
`tests/test_hostel_transfer_recovery.py`, `tests/test_hostel_transfer_postgres.py`
and this document.

Modified: `app/services/hostel_transfer.py`, `app/services/account_deletion.py`,
`app/integrations/mikrotik/client.py`, `app/models/__init__.py`,
`app/core/config.py`, `app/main.py`, `tests/test_hostel_transfer.py`,
`requirements.txt`, `pyproject.toml`, `.env.example` and `README.md`.
