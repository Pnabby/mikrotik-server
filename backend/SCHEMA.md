# Customer account schema

The schema starts at Alembic revision `20260902_0001`; revision `20260903_0002` completes
the database-backed router catalogue and revision `20260903_0003` adds hostel-specific
profile presentation. It separates business truth from router enforcement so a confirmed
payment remains recoverable when RouterOS is offline or returns an uncertain result.

## Core records

- `routers` is the runtime source for each site's identity, display name, VPN host, API
  port, hotspot network, Paystack split code, display order, active state, and health. Shared
  credentials remain outside the database in environment secrets. A configured split code is
  applied only to checkout initialization for a customer assigned to that router.
- `packages` stores business terms; `router_package_profiles` maps each package to the
  exact MikroTik profile available on a router and stores the hostel-specific display name,
  description, and customer-facing download speed. Package validity is optional for plans
  without a fixed duration. The native MikroTik name is never exposed as the sales
  name when a display override is configured.
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

## Admin profile catalogue

The authenticated admin workspace discovers HotSpot user profiles live from the selected
router. Saving a profile creates or updates its package mapping, presentation, commercial
terms, and published state in one transaction. A package shared by multiple routers is
copied before hostel-specific terms are edited, preventing an edit at one hostel from
silently changing another. Every save records the administrator, router, native profile,
display name, price, visibility, and source IP in `audit_logs`.

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

Registration order:

```text
validate account details
  -> confirm the selected router is reachable and has the disabled profile
  -> confirm the username is not already on the selected router
  -> send and verify the email OTP
  -> create RouterOS HotSpot user (profile=disabled, disabled=yes)
  -> read back and verify the marked RouterOS user
  -> hash the PIN with Argon2id
  -> commit the inactive PostgreSQL customer and consume the OTP
```

Customer login order:

```text
normalize the username and verify the Argon2id PIN hash
  -> reject suspended or closed accounts
  -> create a random session token and store only its SHA-256 hash
  -> send the raw token only in an HTTP-only, SameSite cookie
  -> resolve account data from the authenticated customer ID
  -> revoke the stored session during logout
```

If the final PostgreSQL commit fails, the backend removes the RouterOS user only when its
registration marker matches the current OTP challenge. An uncertain RouterOS create is
read back before the operation is classified as failed, making a retry idempotent.

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

### `router_hourly_metrics`

One UTC row per router/hour, incrementally updated by five-minute RouterOS samples. It stores
active-device, CPU, memory, WAN-rate averages and peaks; traffic-counter deltas; interface
availability; uptime; optional temperature/voltage; and failed collection attempts. The
composite `(router_id, hour)` primary key keeps storage bounded and supports hourly demand
forecasting without retaining device identities.

The migration is intentionally not run by application startup. Review it and apply it
explicitly with `alembic upgrade head` when the schema is approved.
