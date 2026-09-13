# Vlad WiFi hotspot monorepo

The project is split into a public React application, a separate React admin application,
and a modular FastAPI backend.

```text
admin/       Admin login and hostel profile-management application
backend/     FastAPI, RouterOS integration, SQLAlchemy models, and Alembic
public/      Customer signup, login, and account React application
```

## Customer portal

The public application now uses account login instead of the former voucher-status lookup.
Customers can create an account, log in with their username and PIN, view their current
plan, see plans available at their hostel, review purchase history, and log out. These
accounts can also be moved to another active hostel from Profile after PIN confirmation.
The move ends RouterOS sessions and remembered logins, carries the hotspot user settings
and comment to the destination, and deducts settled byte usage from finite allowances.
The customer-facing paths and APIs are available:

```text
GET  /
GET  /login
GET  /signup
GET  /account
GET  /profile
GET  /health
GET  /api/routers
GET  /api/registration/username-availability
GET  /api/registration/router-readiness
POST /api/registration/start
POST /api/registration/complete
POST /api/auth/login
POST /api/auth/logout
GET  /api/account
GET  /api/account/hotspot-status
POST /api/account/devices/{session_id}/logout
POST /api/account/transfer-hostel
POST /api/account/delete
```

Successful login creates an opaque, HTTP-only customer session cookie. Only a SHA-256 hash
of the session token is stored in PostgreSQL, sessions expire after
`CUSTOMER_SESSION_TTL_SECONDS`, and logout revokes the stored session. The account endpoint
always resolves the customer from this session; it does not accept a username to inspect.
The same restriction applies to live WiFi status and device disconnection.

## Local setup

Requirements: Python 3.11+, PostgreSQL, and Node.js 20.19+ (or 22.12+).

From the repository root in PowerShell:

```powershell
Copy-Item backend\.env.example backend\.env
python -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
python -m pip install -e ".\backend[dev]"
npm install --prefix public
npm install --prefix admin
```

Configure `backend/.env` before attempting a RouterOS or database operation. Run the backend:

```powershell
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

Run the public frontend in another terminal. Vite proxies `/api` to port 8000:

```powershell
npm run dev --prefix public
```

The public page is then at `http://localhost:5173`. Run the admin login at
`http://localhost:5174` with:

```powershell
npm run dev --prefix admin
```

Create or reset an administrator from the backend directory. The command prompts for the
password without putting it in shell history:

```powershell
.venv\Scripts\python.exe -m app.commands.admins --username admin
```

Admin passwords are stored only as Argon2id hashes. Successful login uses a separate,
HTTP-only admin session cookie. The admin workspace lets an administrator select a hostel,
read its current HotSpot user profiles directly from MikroTik, and configure the display
name, description, price, optional validity, data allowance, device limit, download speed,
and customer visibility for each profile. Selecting **All hostels** shows only profile
names present on every active router and applies one configuration to all of them. Download
speed is prefilled from the RouterOS rate limit when available and can be edited before saving.
The Revenue & Transactions view ranks revenue by plan, breaks revenue down by hostel when
all hostels are selected, and supports all-time, last-7-days, last-30-days, and custom ranges.
Profile changes are written to the audit log. The registration-only profile cannot be
published for purchase. New configurations default to an unlimited device count. Deleting a
configuration removes only its customer-facing plan mapping; it never deletes the profile from
the MikroTik router. Operators and administrators can also move or permanently delete customer
accounts from the user directory after confirming their own admin password.

Admin API routes:

```text
POST /api/admin/auth/login
GET  /api/admin/auth/session
POST /api/admin/auth/logout
GET  /api/admin/hostels
POST /api/admin/hostels/{router_id}/ip-cloud/force-update
GET  /api/admin/hostels/{router_id}/profiles
PUT  /api/admin/hostels/{router_id}/profiles/{mikrotik_profile}
DELETE /api/admin/hostels/{router_id}/profiles/{mikrotik_profile}
POST /api/admin/dashboard/customers/{customer_id}/transfer-hostel
POST /api/admin/dashboard/customers/{customer_id}/delete
```

To build both React applications:

```powershell
npm run build --prefix public
npm run build --prefix admin
```

After `public/dist` exists, FastAPI serves the built public app at `/`, `/login`, `/signup`,
and `/account`. Without a build, those paths redirect to `FRONTEND_URL` so local frontend
development remains separate.

## Configuration

Secrets and application deployment settings are environment-driven. Router catalogue
metadata is stored in PostgreSQL. In particular:

- `MIKROTIK_USERNAME` and `MIKROTIK_PASSWORD` are shared RouterOS credentials.
- The `routers` table is the single runtime source for router IDs, hostel names, VPN hosts,
  API ports, hotspot networks, Paystack split codes, display order, active state, and health.
- `MIKROTIK_ROUTERS_JSON` is supported only as a legacy one-time import input and is never
  used for runtime router resolution.
- `DATABASE_URL` is a PostgreSQL SQLAlchemy URL such as
  `postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE`.
- `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, and `BREVO_SENDER_NAME` configure
  transactional OTP delivery. The sender address must be verified in Brevo.
- `OTP_HASH_SECRET` is an application-only random secret of at least 32 characters used
  to protect stored OTP hashes. It must be different from the Brevo API key.
- `PIN_HASH_SECRET` is a second independent random secret used with Argon2id to protect
  low-entropy customer PIN hashes.
- `CUSTOMER_SESSION_TTL_SECONDS` controls the customer login lifetime and defaults to
  seven days.
- `MIKROTIK_REGISTRATION_PROFILE` is the RouterOS HotSpot profile assigned during signup
  and defaults to `disabled`; the RouterOS user itself is also created disabled.
- `API_CORS_ORIGINS`, `FRONTEND_URL`, and optionally `FRONTEND_DIST_DIR` control
  public-app/backend deployment boundaries.
- `PAYSTACK_SECRET_KEY` and `PAYSTACK_PUBLIC_KEY` hold keys from the same Paystack mode.
  `PAYSTACK_CALLBACK_URL` must be the public HTTPS backend callback URL. Paystack signs
  webhooks with the secret key, so `PAYSTACK_WEBHOOK_SECRET` normally stays empty.
- Each hostel's optional Paystack split code is managed from its admin details. When set,
  it is sent server-side while initializing purchases for customers assigned to that hostel.

For local Paystack testing, expose backend port 8000 through an HTTPS tunnel and configure
these two URLs in the Paystack dashboard, replacing `YOUR_TUNNEL_HOST` with the active host:

```text
Callback URL: https://YOUR_TUNNEL_HOST/api/payments/paystack/callback
Webhook URL:  https://YOUR_TUNNEL_HOST/api/payments/paystack/webhook
```

Quick-tunnel addresses are temporary. When the tunnel changes, update both the dashboard
and `PAYSTACK_CALLBACK_URL` before testing another purchase.

Do not commit `backend/.env`. Database passwords, shared router credentials, Paystack keys,
and other deployment-specific secrets do not have tracked defaults.

## PostgreSQL and migrations

The redesigned schema defines permanent customers, routers, packages and RouterOS profile
mappings, OTP challenges, secure sessions, Paystack transactions/events, activation jobs
and attempts, subscriptions, administrators, and audit logs. Payment state belongs to the
transaction while RouterOS provisioning state belongs to a separate activation record, so
a confirmed payment remains recoverable during a router outage. See
`backend/SCHEMA.md` for the table and state-machine contract.

The application does not run Alembic during startup. After reviewing new migrations and
backing up any target database, apply them manually:

```powershell
Set-Location backend
.venv\Scripts\alembic.exe upgrade head
Set-Location ..
```

Manage routers from the backend directory. These commands never store router credentials:

```powershell
# See the database catalogue
.venv\Scripts\python.exe -m app.commands.routers list

# Add or update a router
.venv\Scripts\python.exe -m app.commands.routers add `
  --id example-hostel `
  --name "Example Hostel" `
  --host 10.0.0.10 `
  --port 8728 `
  --network 192.168.100.0/24 `
  --split-code SPL_xxxxxxxxxx `
  --order 10

# One-time migration from an existing MIKROTIK_ROUTERS_JSON value
.venv\Scripts\python.exe -m app.commands.routers import-env
```

## Validation

```powershell
Set-Location backend
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check app tests
Set-Location ..
npm run lint --prefix public
npm run lint --prefix admin
npm run build --prefix public
npm run build --prefix admin
```

## Architecture boundaries

- `backend/app/routes/` handles HTTP contracts and delegates hotspot work.
- `backend/app/services/` owns hotspot business behavior and reserves separate modules
  for verification, activation, reconciliation, and subscriptions.
- `backend/app/integrations/mikrotik/` contains RouterOS behavior and database catalogue
  resolution.
- `backend/app/integrations/paystack/` owns server-side checkout initialization and
  transaction verification.
- `backend/app/db/` owns the engine/session factory; database access is injectable.
- `public/src/services/` owns HTTP calls while `pages/` owns the signup, login, and
  authenticated account workflows.

Registration email OTP delivery, account provisioning, login sessions, the account
overview, Paystack checkout, signed webhooks, payment verification, and RouterOS package
activation are implemented. Signup creates and verifies a disabled RouterOS HotSpot user
before committing the inactive customer to PostgreSQL. A verified payment is recorded
independently from router activation, and customers can retry a pending activation without
being charged again. Automated scheduled reconciliation and PIN recovery remain separate
vertical slices.
