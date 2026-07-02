# mikrotik

Starter scaffold for a Python project using a `src/` layout.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
pytest
python -m mikrotik
mikrotik-api
```

## Install

Runtime dependencies only:

```powershell
python -m pip install -r requirements.txt
```

Editable install from project metadata:

```powershell
python -m pip install -e .
```

## Structure

```text
src/mikrotik/    Package code
tests/           Test suite
pyproject.toml   Project metadata and tooling
```
