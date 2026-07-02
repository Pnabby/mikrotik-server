# mikrotik

Starter scaffold for a Python project using a `src/` layout.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
pytest
python -m mikrotik
mikrotik-api
```

## Structure

```text
src/mikrotik/    Package code
tests/           Test suite
pyproject.toml   Project metadata and tooling
```
