# Vlad WiFi backend

FastAPI application package for the Vlad WiFi monorepo. See the repository-level
`README.md` for configuration, local run commands, endpoint compatibility, PostgreSQL
setup, and migration safety notes.

The redesigned database contract and failure-safety invariants are documented in
`SCHEMA.md`.

The protected admin API can list hostels, discover live MikroTik HotSpot profiles, and
configure the customer-facing plan name and commercial terms for each hostel. Run the
admin React app on port 5174 from the repository root to use the management workspace.

Development commands from this directory:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check app tests
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Production-compatible ASGI targets:

```text
uvicorn app.main:app --host 0.0.0.0 --port 8000
gunicorn app.main:app -k uvicorn_worker.UvicornWorker --bind 0.0.0.0:8000
```

Alembic never runs automatically. Set `DATABASE_URL`, inspect the migration, back up the
target database, and run `alembic upgrade head` explicitly.

To transfer the current hostel catalogue and administrator logins to a new database,
export a private seed bundle from the source database:

```powershell
.venv\Scripts\python.exe -m app.commands.seed --export seed-data.private.json
```

The bundle contains Argon2 password hashes, never plaintext passwords, and is ignored by
Git. Copy it to the server through a private channel. After running migrations against the
new `DATABASE_URL`, import it with:

```bash
python -m app.commands.seed --import seed-data.private.json
```

Importing is idempotent: matching hostel IDs and administrator usernames are updated, and
missing records are created. Existing admin sessions are revoked if an imported password
hash changes. Delete the bundle from the server after a successful import.

Router metadata is managed in PostgreSQL while the shared `MIKROTIK_USERNAME` and
`MIKROTIK_PASSWORD` remain in `.env`. Use the catalogue commands from this directory:

```powershell
.venv\Scripts\python.exe -m app.commands.routers list
.venv\Scripts\python.exe -m app.commands.routers add --help
```
