# FLINT WiFi hotspot monorepo

The project is split into a public React application, a separate React admin application,
and a modular FastAPI backend.

```text
admin/       Admin React application boundary (screens intentionally deferred)
backend/     FastAPI, RouterOS integration, SQLAlchemy models, and Alembic
public/      Public hotspot status React application
```

## What remains compatible

The status page keeps its original stylesheet, layout, colors, spacing, loading overlay,
voucher lookup, device classification, current-device badge, logout confirmation, and
public error messages. These existing paths remain available:

```text
GET  /
GET  /status
GET  /status/{username}
GET  /launch-status
POST /launch-status
GET  /health
GET  /api/routers
GET  /api/routers/{router_id}/hotspot/users/{username}/status
POST /api/routers/{router_id}/hotspot/user-lookup
POST /api/routers/{router_id}/hotspot/users/{username}/devices/{session_id}/logout
```

`GET /api/status-session` is the only new public-page endpoint. It exposes the locked
status username, selected router, and current device identifiers to React without making
the existing HTTP-only cookies readable by JavaScript. Query-string usernames are still
ignored; only the launch flow can set the locked username.

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

The public page is then at `http://localhost:5173`. Run the separate admin boundary at
`http://localhost:5174` with:

```powershell
npm run dev --prefix admin
```

To build both React applications:

```powershell
npm run build --prefix public
npm run build --prefix admin
```

After `public/dist` exists, FastAPI serves the built public app at `/`, `/status`, and
`/status/{username}`. Without a build, those paths redirect to `FRONTEND_URL` so local
frontend development remains separate.

## Configuration

All credentials and deployment addresses are environment-driven. In particular:

- `MIKROTIK_USERNAME` and `MIKROTIK_PASSWORD` are shared RouterOS credentials.
- `MIKROTIK_ROUTERS_JSON` is the server-side allowlist. Each JSON item contains
  `router_id`, `name`, `host`, `port`, and `hotspot_network`.
- `DATABASE_URL` is a PostgreSQL SQLAlchemy URL such as
  `postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE`.
- `API_CORS_ORIGINS`, `FRONTEND_URL`, and optionally `FRONTEND_DIST_DIR` control
  public-app/backend deployment boundaries.
- Paystack environment names are reserved, but no payment implementation is enabled.

Do not commit `backend/.env`. Router connection hosts, database passwords, Paystack keys, and
other deployment-specific values do not have tracked defaults.

## PostgreSQL and migrations

The redesigned schema defines permanent customers, routers, packages and RouterOS profile
mappings, OTP challenges, secure sessions, Paystack transactions/events, activation jobs
and attempts, subscriptions, administrators, and audit logs. Payment state belongs to the
transaction while RouterOS provisioning state belongs to a separate activation record, so
a confirmed payment remains recoverable during a router outage. See
`backend/SCHEMA.md` for the table and state-machine contract.

No database existed in the previous code, so there is no legacy data migration to run.
The application does not connect to PostgreSQL or run Alembic during startup. After
reviewing the initial migration and backing up any target database, apply it manually:

```powershell
Set-Location backend
.venv\Scripts\alembic.exe upgrade head
Set-Location ..
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
- `backend/app/integrations/mikrotik/` contains all RouterOS behavior and its allowlist.
- `backend/app/integrations/paystack/` is the future Paystack adapter boundary.
- `backend/app/db/` owns the engine/session factory; database access is injectable.
- `public/src/services/` owns HTTP calls, `hooks/` owns page workflows, and
  `components/` owns the existing visual sections and dialogs.

The database boundaries for permanent accounts, OTP, PIN recovery, Paystack processing,
activation/retry jobs, reconciliation, and history are defined. Their service and user
interface workflows remain to be implemented one vertical slice at a time.
