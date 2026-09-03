# FLINT WiFi backend

FastAPI application package for the FLINT WiFi monorepo. See the repository-level
`README.md` for configuration, local run commands, endpoint compatibility, PostgreSQL
setup, and migration safety notes.

The redesigned database contract and failure-safety invariants are documented in
`SCHEMA.md`.

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
