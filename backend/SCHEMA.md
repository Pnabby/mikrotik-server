# Customer account schema

The initial schema is defined by Alembic revision `20260902_0001`. It separates business
truth from router enforcement so a confirmed payment remains recoverable when RouterOS is
offline or returns an uncertain result.

## Core records

- `routers` stores the database identity and health of each configured site.
- `packages` stores business terms; `router_package_profiles` maps each package to the
  exact MikroTik profile available on a router.
- `customers` stores permanent accounts, normalized email/username values, the assigned
  router, and only an irreversible `pin_hash`.
- `email_otp_challenges`, `customer_sessions`, and `admin_sessions` store only hashes of
  OTP/session secrets.
- `transactions` owns Paystack/payment state. `payment_events` provides durable webhook
  idempotency and processing history.
- `activations` owns the desired RouterOS state and its independent status.
  `activation_attempts` records the router state observed before and after every attempt.
- `subscriptions` starts only after activation is confirmed and links the customer,
  transaction, activation, package, and router.
- `admin_users` and `audit_logs` provide role-based administration and durable change
  history without exposing customer PINs.

## State machines

Payment states:

```text
pending -> success
pending -> failed
```

Activation states:

```text
not_started -> processing -> provisioning -> success
                              |-> retry_required
                              |-> reconciliation_required
                              |-> manual_review
                              |-> superseded
```

Subscription states:

```text
pending -> active -> expired
                  |-> cancelled
                  |-> superseded
```

## Failure-safety invariants

- Payment and activation states are stored in different tables.
- Paystack references and webhook event keys are unique.
- Each transaction has at most one activation and one subscription.
- Activation IDs and monotonic sequence numbers are unique. The sequence number lets
  reconciliation distinguish a known older router marker from a newer one.
- Desired profile/disabled state is committed before RouterOS is changed.
- Each activation attempt number is unique per activation and can retain read-before-write
  evidence plus its classified outcome.
- Subscription time fields remain nullable until activation succeeds, and expiration must
  be later than the start time.
- No table contains a plaintext customer PIN, OTP code, or session token.

The migration is intentionally not run by application startup. Review it and apply it
explicitly with `alembic upgrade head` when the schema is approved.
